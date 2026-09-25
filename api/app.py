from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import json
import math
import os
import pandas as pd
import shutil
import sqlite3
import tempfile
import urllib.request
from datetime import datetime
from urllib.parse import urlparse
from urllib.request import url2pathname
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
try:
    from .ml_train import BEST_MODEL_PATH, MODEL_INFO_PATH, train_new_model
    from .auth import auth_bp, configure_auth, login_required, roles_required
    from .analytics import analytics_bp, configure_analytics
    from .database import initialize_database
except ImportError:
    from ml_train import BEST_MODEL_PATH, MODEL_INFO_PATH, train_new_model
    from auth import auth_bp, configure_auth, login_required, roles_required
    from analytics import analytics_bp, configure_analytics
    from database import initialize_database

app = Flask(__name__)
ALLOWED_CORS_ORIGINS = [
    "https://nnworking2425-lang.github.io",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.0.0.1:5000",
    "http://localhost:5000",
]
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", ",".join(ALLOWED_CORS_ORIGINS)).split(",")
    if origin.strip()
]
CORS(
    app,
    resources={r"/*": {"origins": allowed_origins}},
    supports_credentials=True,
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "Access-Control-Request-Method",
        "Access-Control-Request-Headers",
    ],
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    expose_headers=["Content-Type", "Authorization"],
    max_age=600,
)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    host = request.headers.get("Host", "")
    is_local_host = "localhost" in host or "127.0.0.1" in host

    if origin in allowed_origins or is_local_host:
        response.headers["Access-Control-Allow-Origin"] = origin or "http://127.0.0.1:8000"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"

    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Origin"] = origin or "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = (
            "Content-Type, Authorization, X-Requested-With, "
            "Access-Control-Request-Method, Access-Control-Request-Headers"
        )
        response.headers["Access-Control-Max-Age"] = "600"

    return response


@app.route("/")
def home():
    return {
        "status": "running",
        "service": "AI Sales Intelligence API"
    }


@app.before_request
def debug_model_state():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_production_model()
    print("MODEL OBJECT:", MODEL)


@app.route("/health", methods=["GET", "OPTIONS"])
def health():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_production_model()
    return jsonify({
        "status": "ok",
        "service": "AI Sales Intelligence API",
        "model_loaded": MODEL is not None
    })


def get_latest_prediction_payload():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    row = connection.execute("""
        SELECT predicted_revenue, created_at
        FROM prediction_history
        ORDER BY id DESC
        LIMIT 1
    """).fetchone()
    connection.close()

    if row is None or row["predicted_revenue"] is None:
        return {
            "latest_forecast": 0.0,
            "latest": 0.0,
            "predicted_revenue": 0.0,
            "recent_prediction": 0.0,
            "created_at": None,
            "value": 0.0,
        }

    value = float(row["predicted_revenue"])
    rounded = round(value, 2)
    return {
        "latest_forecast": rounded,
        "latest": rounded,
        "predicted_revenue": rounded,
        "recent_prediction": rounded,
        "created_at": row["created_at"],
        "value": rounded,
    }


@app.route("/dashboard", methods=["GET", "OPTIONS"])
@app.route("/api/dashboard", methods=["GET", "OPTIONS"])
@login_required
def dashboard_api():
    performance_response = model_performance()
    analytics_handler = app.view_functions.get("analytics.analytics")
    analytics_response = analytics_handler() if analytics_handler else jsonify({})
    model_info_response = model_info()

    performance_payload = performance_response.get_json(silent=True) if hasattr(performance_response, "get_json") else {}
    analytics_payload = analytics_response.get_json(silent=True) if hasattr(analytics_response, "get_json") else {}
    model_info_payload = model_info_response.get_json(silent=True) if hasattr(model_info_response, "get_json") else {}
    latest_prediction = get_latest_prediction_payload()

    r2_value = performance_payload.get("r2_accuracy", performance_payload.get("r2", 0))
    sample_value = performance_payload.get("test_samples", performance_payload.get("samples", 0))

    return jsonify({
        "r2": r2_value,
        "r2_accuracy": r2_value,
        "mae": performance_payload.get("mae", 0),
        "rmse": performance_payload.get("rmse", 0),
        "samples": sample_value,
        "test_samples": sample_value,
        "total_revenue": analytics_payload.get("total_revenue", 0),
        "average_revenue": analytics_payload.get("average_revenue", analytics_payload.get("average_order_value", 0)),
        "average_order_value": analytics_payload.get("average_revenue", analytics_payload.get("average_order_value", 0)),
        "growth": analytics_payload.get("growth_rate", analytics_payload.get("growth", 0)),
        "growth_rate": analytics_payload.get("growth_rate", analytics_payload.get("growth", 0)),
        "model": model_info_payload.get("model", ""),
        "best_sales_day": analytics_payload.get("best_sales_day"),
        "highest_revenue": analytics_payload.get("highest_revenue", 0),
        "latest_prediction": latest_prediction["latest_forecast"],
        "latest_forecast": latest_prediction["latest_forecast"],
        "latest": latest_prediction["latest"],
        "predicted_revenue": latest_prediction["predicted_revenue"],
        "recent_prediction": latest_prediction["recent_prediction"],
        "created_at": latest_prediction["created_at"],
    })


@app.route("/api/model-info")
@login_required
def api_model_info():
    return model_info()


@app.route("/api/analytics")
@login_required
def api_analytics():
    analytics_handler = app.view_functions.get("analytics.analytics")
    if analytics_handler is None:
        return jsonify({})
    return analytics_handler()


def load_environment_file(path):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_environment_file(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "development-only-change-me")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["JSON_SORT_KEYS"] = False
app.config["SESSION_COOKIE_HTTPONLY"] = True
is_production = os.getenv("FLASK_ENV") == "production" or bool(os.getenv("RENDER")) or os.getenv("APP_ENV") == "production"
app.config["SESSION_COOKIE_SAMESITE"] = "None" if is_production else "Lax"
app.config["SESSION_COOKIE_SECURE"] = is_production


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "model"))
MODEL_PATH = os.path.abspath(os.path.join(MODEL_DIR, "production_model.pkl"))
MODEL = None


def resolve_project_path(configured_path, default_path):
    if not configured_path:
        return default_path
    if os.path.isabs(configured_path):
        return configured_path
    return os.path.abspath(os.path.join(BASE_DIR, "..", configured_path))


def load_saved_model_metadata():
    fallback_features = FEATURE_NAMES.copy()
    fallback_defaults = {}

    if not os.path.exists(MODEL_INFO_PATH):
        return fallback_features, fallback_defaults

    try:
        with open(MODEL_INFO_PATH, "r", encoding="utf-8") as file:
            saved_info = json.load(file)
        features = saved_info.get("features") or fallback_features
        defaults = saved_info.get("feature_defaults") or fallback_defaults
        return list(features), defaults
    except (json.JSONDecodeError, OSError, TypeError):
        return fallback_features, fallback_defaults


def is_git_lfs_pointer_file(file_path):
    if not file_path or not os.path.exists(file_path):
        return False
    try:
        with open(file_path, "rb") as handle:
            header = handle.read(256)
    except OSError:
        return False

    return header.startswith(b"version https://git-lfs.github.com/spec/v1")


def rebuild_model_artifacts():
    if not os.path.exists(DATASET_PATH):
        return False

    try:
        result = train_new_model(DATASET_PATH)
    except Exception as exc:
        app.logger.warning("Model retraining failed: %s", exc)
        return False

    if result.get("status") != "success":
        app.logger.warning("Model retraining returned unsuccessful status: %s", result)
        return False

    best_model_path = os.path.join(MODEL_DIR, "best_sales_model.pkl")
    if not os.path.exists(best_model_path):
        app.logger.warning("Retraining succeeded but no model file was produced at %s", best_model_path)
        return False

    for file_name in ["production_model.pkl", "random_forest_sales.pkl"]:
        destination = os.path.join(MODEL_DIR, file_name)
        try:
            shutil.copyfile(best_model_path, destination)
        except OSError as exc:
            app.logger.warning("Could not copy trained model to %s: %s", destination, exc)

    return True


MODEL_DOWNLOAD_PATH = os.path.join(BASE_DIR, "model", "production_model.pkl")
MODEL_PKL_PATH = os.path.join(BASE_DIR, "model", "model.pkl")
FALLBACK_MODEL_PATH = resolve_project_path(
    os.getenv("MODEL_PATH"),
    MODEL_PATH
)
MODEL_DIR_CANDIDATES = [
    os.path.join(BASE_DIR, "model"),
    os.path.join(PROJECT_ROOT, "model"),
    os.path.join(PROJECT_ROOT, "api", "model"),
]
MODEL_FILE_NAMES = [
    "model.pkl",
    "production_model.pkl",
    "best_sales_model.pkl",
    "random_forest_sales.pkl",
]

DATASET_PATH = os.path.join(
    BASE_DIR,
    "..",
    "AI_SalesDataset_Orange.csv"
)

FEATURE_NAMES = [
    "OrderCount",
    "QuantitySold",
    "Revenue_Lag1",
    "Revenue_Lag2",
    "Revenue_Lag3",
    "Quantity_Lag1"
]

DATABASE_PATH = resolve_project_path(
    os.getenv("DATABASE_PATH"),
    os.path.join(BASE_DIR, "instance", "sales.db")
)

configure_auth(DATABASE_PATH)
configure_analytics(DATABASE_PATH)
app.register_blueprint(auth_bp)
app.register_blueprint(analytics_bp)
os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
initialize_database(DATABASE_PATH)


def download_model_from_url(model_url, destination_path=MODEL_DOWNLOAD_PATH):
    if not model_url:
        return None

    try:
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)

        if model_url.startswith("file://"):
            parsed_url = urlparse(model_url)
            local_path = parsed_url.path
            if parsed_url.netloc and parsed_url.netloc not in {"", "localhost"}:
                local_path = f"//{parsed_url.netloc}{parsed_url.path}"
            normalized_path = os.path.abspath(os.path.normpath(url2pathname(local_path)))
            if not os.path.exists(normalized_path):
                raise FileNotFoundError(f"Model file does not exist: {normalized_path}")
            with open(normalized_path, "rb") as source_file:
                with open(destination_path, "wb") as local_file:
                    shutil.copyfileobj(source_file, local_file)
            return destination_path

        with urllib.request.urlopen(model_url, timeout=60) as remote_response:
            with open(destination_path, "wb") as local_file:
                shutil.copyfileobj(remote_response, local_file)
        return destination_path
    except Exception as error:
        app.logger.warning("Failed to download production model from MODEL_URL: %s", error)
        return None


def load_production_model():
    candidate_paths = [
        os.path.abspath(os.path.join(BASE_DIR, "model", "production_model.pkl")),
        os.path.abspath(os.path.join(BASE_DIR, "model", "best_sales_model.pkl")),
        os.path.abspath(os.path.join(BASE_DIR, "model", "random_forest_sales.pkl")),
    ]

    print("CURRENT WORKING DIRECTORY:", os.getcwd())
    print("MODEL CHECK PATHS:", candidate_paths)
    for active_model_path in candidate_paths:
        print(f"MODEL PATH: {active_model_path} | EXISTS={os.path.exists(active_model_path)}")

    for active_model_path in candidate_paths:
        if not os.path.exists(active_model_path):
            continue
        if is_git_lfs_pointer_file(active_model_path):
            app.logger.warning("Skipping Git LFS pointer model artifact: %s", active_model_path)
            continue

        try:
            loaded_model = joblib.load(active_model_path)
        except Exception as exc:
            print(f"MODEL LOAD FAILED for {active_model_path}: {exc}")
            continue

        print("LOADED MODEL TYPE:", type(loaded_model).__name__)
        loaded_feature_names = getattr(loaded_model, "feature_names_in_", None)
        if loaded_feature_names is not None and list(loaded_feature_names) != FEATURE_NAMES:
            print(f"MODEL FEATURE MISMATCH for {active_model_path}: expected {FEATURE_NAMES}")
            continue
        if getattr(loaded_model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
            print(f"MODEL FEATURE COUNT MISMATCH for {active_model_path}")
            continue

        print("MODEL LOADED FROM:", active_model_path)
        return loaded_model, FEATURE_NAMES.copy(), {}

    print("No compatible model file found. Attempting to rebuild from training dataset.")
    if rebuild_model_artifacts():
        for active_model_path in candidate_paths:
            if not os.path.exists(active_model_path):
                continue
            try:
                loaded_model = joblib.load(active_model_path)
            except Exception as exc:
                print(f"MODEL RELOAD FAILED for {active_model_path}: {exc}")
                continue
            loaded_feature_names = getattr(loaded_model, "feature_names_in_", None)
            if loaded_feature_names is not None and list(loaded_feature_names) != FEATURE_NAMES:
                continue
            if getattr(loaded_model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
                continue
            print("MODEL LOADED FROM REBUILD:", active_model_path)
            return loaded_model, FEATURE_NAMES.copy(), {}

    app.logger.warning("No compatible model file found. Checked paths: %s", candidate_paths)
    saved_features, saved_defaults = load_saved_model_metadata()
    return None, saved_features, saved_defaults


def load_model():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    print("CURRENT WORKING DIRECTORY:", os.getcwd())
    print("MODEL CHECK PATHS:", [
        os.path.abspath(os.path.join(BASE_DIR, "model", "production_model.pkl")),
        os.path.abspath(os.path.join(BASE_DIR, "model", "best_sales_model.pkl")),
        os.path.abspath(os.path.join(BASE_DIR, "model", "random_forest_sales.pkl")),
    ])

    model, feature_names, defaults = load_production_model()
    if model is None:
        raise FileNotFoundError("No compatible model file found in api/model directory.")

    MODEL = model
    ACTIVE_FEATURE_NAMES = feature_names
    ACTIVE_FEATURE_DEFAULTS = defaults
    print("MODEL TYPE:", type(MODEL).__name__)
    print("MODEL LOADED:", MODEL is not None)
    return MODEL


def load_active_model():
    return get_model()


def get_model():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        try:
            MODEL = load_model()
        except FileNotFoundError as exc:
            app.logger.warning("%s", exc)
            return None, FEATURE_NAMES.copy(), {}
    return MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS


MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = get_model()
print("CURRENT WORKING DIRECTORY:", os.getcwd())
print("MODEL PATH:", MODEL_PATH)
print("MODEL EXISTS:", os.path.exists(MODEL_PATH))
print("MODEL TYPE:", type(MODEL) if MODEL is not None else None)
print("MODEL LOADED:", MODEL is not None)
if MODEL is None:
    app.logger.warning("No compatible model file found. Set MODEL_PATH or MODEL_URL to provide a production model.")


# ==========================
# DATABASE
# ==========================

def create_table():

    conn = sqlite3.connect(DATABASE_PATH)

    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS history(

        Date TEXT,
        OrderCount REAL,
        QuantitySold REAL,
        Revenue_Lag1 REAL,
        Revenue_Lag2 REAL,
        Revenue_Lag3 REAL,
        Quantity_Lag1 REAL,
        PredictedRevenue REAL

    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS prediction_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at DATETIME,
        order_count INTEGER,
        quantity_sold INTEGER,
        revenue_lag1 FLOAT,
        revenue_lag2 FLOAT,
        revenue_lag3 FLOAT,
        quantity_lag1 INTEGER,
        actual_revenue FLOAT,
        predicted_revenue FLOAT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS model_training_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT,
        r2_score FLOAT,
        mae FLOAT,
        rmse FLOAT,
        created_at DATETIME
    )
    """)

    prediction_history_columns = [
        row[1]
        for row in c.execute("PRAGMA table_info(prediction_history)").fetchall()
    ]
    if "actual_revenue" not in prediction_history_columns:
        c.execute(
            "ALTER TABLE prediction_history ADD COLUMN actual_revenue FLOAT"
        )
    c.execute("""
        UPDATE prediction_history
        SET actual_revenue = revenue_lag1
        WHERE actual_revenue IS NULL
    """)

    conn.commit()
    conn.close()


create_table()


# ==========================
# PREDICT API
# ==========================

@app.route("/test", methods=["GET"])
def test():
    return jsonify({"status": "API OK"})

@app.route("/predict", methods=["POST"])
def predict():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    model = MODEL
    if model is None:
        try:
            model = load_model()
        except FileNotFoundError as exc:
            return jsonify({
                "error": str(exc)
            }), 503
    print("MODEL STATUS:", model is not None)
    print("model type:", type(model).__name__)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object."}), 400

    print("received_data:", data)

    feature_order = list(getattr(model, "feature_names_in_", ACTIVE_FEATURE_NAMES or FEATURE_NAMES))
    feature_aliases = {
        "OrderCount": ["OrderCount", "order_count", "orderCount"],
        "QuantitySold": ["QuantitySold", "quantity_sold", "quantitySold"],
        "Revenue_Lag1": ["Revenue_Lag1", "revenue_lag1", "revenueLag1"],
        "Revenue_Lag2": ["Revenue_Lag2", "revenue_lag2", "revenueLag2"],
        "Revenue_Lag3": ["Revenue_Lag3", "revenue_lag3", "revenueLag3"],
        "Quantity_Lag1": ["Quantity_Lag1", "quantity_lag1", "quantityLag1"],
    }

    normalized_input = {}
    for key, value in data.items():
        if value is None:
            continue
        normalized_input[str(key)] = value

    payload_by_canonical = {}
    for canonical_name, alias_names in feature_aliases.items():
        for alias in alias_names:
            if alias in normalized_input:
                payload_by_canonical[canonical_name] = normalized_input[alias]
                break

    missing_fields = [field for field in feature_order if field not in payload_by_canonical]
    if missing_fields:
        return jsonify({
            "error": f"Missing required fields: {', '.join(missing_fields)}"
        }), 400

    try:
        input_values = {
            name: float(payload_by_canonical[name])
            for name in feature_order
        }
        ordered_features = pd.DataFrame(
            [[input_values[name] for name in feature_order]],
            columns=feature_order
        )
        print("ordered_features:")
        print(ordered_features)
        raw_model_prediction = model.predict(ordered_features)[0]
        prediction = round(float(raw_model_prediction), 2)
        print("raw model.predict result:", raw_model_prediction)
        print("final prediction:", prediction)
    except Exception as exc:
        return jsonify({
            "error": str(exc)
        }), 500

    prediction = round(float(prediction), 2)


    # lưu history

    conn = sqlite3.connect(DATABASE_PATH)

    c = conn.cursor()


    c.execute("""
    INSERT INTO history (
        Date,
        OrderCount,
        QuantitySold,
        Revenue_Lag1,
        Revenue_Lag2,
        Revenue_Lag3,
        Quantity_Lag1,
        PredictedRevenue
    ) VALUES (?,?,?,?,?,?,?,?)
    """,
    (

        datetime.now().strftime(
            "%Y-%m-%d %H:%M"
        ),

        input_values["OrderCount"],
        input_values["QuantitySold"],
        input_values["Revenue_Lag1"],
        input_values["Revenue_Lag2"],
        input_values["Revenue_Lag3"],
        input_values["Quantity_Lag1"],
        prediction

    ))

    c.execute("""
    INSERT INTO prediction_history (
        created_at,
        order_count,
        quantity_sold,
        revenue_lag1,
        revenue_lag2,
        revenue_lag3,
        quantity_lag1,
        actual_revenue,
        predicted_revenue
    ) VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        int(input_values["OrderCount"]),
        int(input_values["QuantitySold"]),
        input_values["Revenue_Lag1"],
        input_values["Revenue_Lag2"],
        input_values["Revenue_Lag3"],
        int(input_values["Quantity_Lag1"]),
        input_values["Revenue_Lag1"],
        prediction
    ))


    conn.commit()
    conn.close()



    return jsonify({

        "predicted_revenue": prediction

    })


# ==========================
# PREDICTION HISTORY API
# ==========================

@app.route("/prediction-history", methods=["GET"])
@login_required
def prediction_history():

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT created_at, order_count, actual_revenue, predicted_revenue
        FROM prediction_history
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()

    conn.close()

    return jsonify([
        dict(row)
        for row in rows
    ])


@app.route("/api/latest-prediction", methods=["GET", "OPTIONS"])
@app.route("/latest-prediction", methods=["GET", "OPTIONS"])
@login_required
def latest_prediction():
    return jsonify(get_latest_prediction_payload())


# ==========================
# MODEL TRAINING API
# ==========================

@app.route("/train", methods=["POST"])
@roles_required("Admin")
def train():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS

    uploaded_file = request.files.get("file")
    if uploaded_file is None or uploaded_file.filename == "":
        return jsonify({
            "status": "error",
            "message": "Upload a CSV file using the file field."
        }), 400
    if not uploaded_file.filename.lower().endswith(".csv"):
        return jsonify({
            "status": "error",
            "message": "Only CSV files are accepted."
        }), 400

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temporary_file:
            temporary_path = temporary_file.name
        uploaded_file.save(temporary_path)

        result = train_new_model(temporary_path)
        if result["status"] != "success":
            return jsonify(result), 400

        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_active_model()

        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("""
        INSERT INTO model_training_history (
            model_name,
            r2_score,
            mae,
            rmse,
            created_at
        ) VALUES (?,?,?,?,?)
        """, (
            result["model"],
            result["r2"],
            result["mae"],
            result["rmse"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "model": result["model"],
            "r2": result["r2"],
            "message": "New model trained successfully"
        })
    except Exception as error:
        return jsonify({
            "status": "error",
            "message": str(error)
        }), 400
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.remove(temporary_path)


@app.route("/model-training-history", methods=["GET"])
@login_required
def model_training_history():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT model_name, r2_score, mae, rmse, created_at
        FROM model_training_history
        ORDER BY id DESC
        LIMIT 20
    """).fetchall()
    conn.close()

    return jsonify([dict(row) for row in rows])


@app.route("/model-info", methods=["GET"])
@login_required
def model_info():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_production_model()
    model = MODEL

    if model is not None:
        payload = {
            "model": type(model).__name__,
            "features": ACTIVE_FEATURE_NAMES,
            "r2": 0,
            "mae": 0,
            "rmse": 0,
            "samples": 0,
        }
        if os.path.exists(MODEL_INFO_PATH):
            with open(MODEL_INFO_PATH, "r", encoding="utf-8") as file:
                metadata = json.load(file)
            payload.update(metadata)
        return jsonify(payload)

    if os.path.exists(MODEL_INFO_PATH):
        with open(MODEL_INFO_PATH, "r", encoding="utf-8") as file:
            return jsonify(json.load(file))

    return jsonify({
        "model": type(model).__name__ if model is not None else "None",
        "features": ACTIVE_FEATURE_NAMES
    })


# ==========================
# MODEL PERFORMANCE API
# ==========================

@app.route("/model-performance", methods=["GET"])
@login_required
def model_performance():
    model, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = get_model()

    if model is None:
        return jsonify({
            "r2": 0,
            "mae": 0,
            "rmse": 0,
            "samples": 0,
            "message": "Model is not available in the current deployment."
        })

    data = pd.read_csv(DATASET_PATH)

    if "ActualRevenue" not in data.columns or not set(ACTIVE_FEATURE_NAMES).issubset(data.columns):
        if os.path.exists(MODEL_INFO_PATH):
            with open(MODEL_INFO_PATH, "r", encoding="utf-8") as file:
                saved_info = json.load(file)
            return jsonify({
                "r2": saved_info.get("r2", 0),
                "mae": saved_info.get("mae", 0),
                "rmse": saved_info.get("rmse", 0),
                "samples": saved_info.get("samples", 0)
            })

    X = data[ACTIVE_FEATURE_NAMES]
    y = data["ActualRevenue"]

    _, X_test, _, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42
    )

    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    rmse = math.sqrt(mean_squared_error(y_test, y_pred))
    r2 = r2_score(y_test, y_pred)

    sample_count = int(len(y_test))
    r2_accuracy = round(float(r2), 4)

    return jsonify({
        "r2": r2_accuracy,
        "r2_accuracy": r2_accuracy,
        "mae": round(float(mae), 2),
        "rmse": round(float(rmse), 2),
        "samples": sample_count,
        "test_samples": sample_count
    })



# ==========================
# HISTORY
# ==========================

@app.route("/history")
@login_required
def history():

    conn = sqlite3.connect(DATABASE_PATH)

    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM history"
    ).fetchall()


    conn.close()


    return jsonify(
        [
            dict(row)
            for row in rows
        ]
    )



@app.route("/history", methods=["DELETE"])
@roles_required("Admin")
def delete_history():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("DELETE FROM prediction_history")
    conn.execute("DELETE FROM history")
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False
    )
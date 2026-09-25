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
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Vary"] = "Origin"

    if request.method == "OPTIONS":
        response.headers["Access-Control-Allow-Origin"] = origin if origin in allowed_origins else "*"
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
        "average_order_value": analytics_payload.get("average_revenue", 0),
        "growth": analytics_payload.get("growth_rate", 0),
        "model": model_info_payload.get("model", ""),
        "best_sales_day": analytics_payload.get("best_sales_day"),
        "highest_revenue": analytics_payload.get("highest_revenue", 0)
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
MODEL_PATH = os.path.join(BASE_DIR, "model", "production_model.pkl")
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
    configured_model_path = os.getenv("MODEL_PATH")
    if configured_model_path:
        configured_model_path = resolve_project_path(configured_model_path, configured_model_path)

    downloaded_model_path = None
    model_url = os.getenv("MODEL_URL")
    if model_url:
        downloaded_model_path = MODEL_DOWNLOAD_PATH if os.path.exists(MODEL_DOWNLOAD_PATH) else download_model_from_url(model_url)

    candidate_paths = [
        MODEL_PATH,
        configured_model_path,
        downloaded_model_path,
        MODEL_DOWNLOAD_PATH,
        MODEL_PKL_PATH,
        BEST_MODEL_PATH,
        FALLBACK_MODEL_PATH,
    ]

    for model_dir in MODEL_DIR_CANDIDATES:
        for file_name in MODEL_FILE_NAMES:
            candidate_paths.append(os.path.join(model_dir, file_name))

    candidate_paths.extend([
        os.path.join(PROJECT_ROOT, "api", "model", "production_model.pkl"),
        os.path.join(PROJECT_ROOT, "model", "production_model.pkl"),
        os.path.join(PROJECT_ROOT, "model", "model.pkl"),
        os.path.join(PROJECT_ROOT, "model", "random_forest_sales.pkl"),
    ])

    candidate_paths = [path for path in dict.fromkeys(candidate_paths) if path]
    app.logger.info("MODEL LOOKUP CANDIDATES: %s", candidate_paths)

    for active_model_path in candidate_paths:
        if not os.path.exists(active_model_path):
            continue

        try:
            loaded_model = joblib.load(active_model_path)
        except Exception:
            continue

        loaded_feature_names = getattr(loaded_model, "feature_names_in_", None)
        if loaded_feature_names is not None and list(loaded_feature_names) != FEATURE_NAMES:
            continue
        if getattr(loaded_model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
            continue

        app.logger.info("MODEL LOADED FROM: %s", active_model_path)
        return loaded_model, FEATURE_NAMES.copy(), {}

    app.logger.warning("No compatible model file found. Checked paths: %s", candidate_paths)
    saved_features, saved_defaults = load_saved_model_metadata()
    return None, saved_features, saved_defaults


def load_model():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_production_model()
    print("MODEL PATH:", MODEL_PATH)
    print("MODEL EXISTS:", os.path.exists(MODEL_PATH))
    print("MODEL LOADED:", MODEL is not None)
    return MODEL


def load_active_model():
    return get_model()


def get_model():
    global MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS
    if MODEL is None:
        MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = load_production_model()
    return MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS


MODEL, ACTIVE_FEATURE_NAMES, ACTIVE_FEATURE_DEFAULTS = get_model()
print("MODEL PATH:", MODEL_PATH)
print("MODEL EXISTS:", os.path.exists(MODEL_PATH))
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
        model = load_model()
    print("MODEL STATUS:", model is not None)

    data = request.json
    print(request.json)

    try:
        input_values = {
            name: float(data[name])
            for name in ACTIVE_FEATURE_NAMES
        }
        ordered_features = pd.DataFrame(
            [[input_values[name] for name in ACTIVE_FEATURE_NAMES]],
            columns=ACTIVE_FEATURE_NAMES
        )
        prediction = model.predict(ordered_features)[0]
    except (KeyError, TypeError, ValueError):
        return jsonify({
            "error": "All six prediction inputs must be numeric."
        }), 400

    print("OUTPUT:", prediction)
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
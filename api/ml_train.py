import json
import math
import os
from datetime import date

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "model")
BEST_MODEL_PATH = os.path.join(MODEL_DIR, "random_forest_sales.pkl")
MODEL_INFO_PATH = os.path.join(MODEL_DIR, "model_info.json")
TARGET_COLUMN = "ActualRevenue"
FEATURE_COLUMNS = [
    "OrderCount",
    "QuantitySold",
    "Revenue_Lag1",
    "Revenue_Lag2",
    "Revenue_Lag3",
    "Quantity_Lag1"
]


def train_new_model(csv_path):
    data = pd.read_csv(csv_path)

    required_columns = FEATURE_COLUMNS + [TARGET_COLUMN]
    missing_columns = [
        column for column in required_columns
        if column not in data.columns
    ]
    if missing_columns:
        return {
            "status": "error",
            "message": "CSV is missing required columns.",
            "missing_columns": missing_columns
        }

    training_data = data[required_columns].dropna()
    if len(training_data) < 5:
        return {
            "status": "error",
            "message": "CSV must contain at least five complete data rows."
        }

    X = training_data[FEATURE_COLUMNS]
    y = training_data[TARGET_COLUMN]
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42
    )

    model = RandomForestRegressor(
        n_estimators=100,
        random_state=42
    )
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)
    metrics = {
        "model": "RandomForestRegressor",
        "estimator": model,
        "r2": float(r2_score(y_test, predictions)),
        "mae": float(mean_absolute_error(y_test, predictions)),
        "rmse": math.sqrt(mean_squared_error(y_test, predictions))
    }
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(metrics["estimator"], BEST_MODEL_PATH)

    model_info = {
        "model": metrics["model"],
        "r2": round(metrics["r2"], 4),
        "mae": round(metrics["mae"], 2),
        "rmse": round(metrics["rmse"], 2),
        "samples": int(len(y_test)),
        "features": FEATURE_COLUMNS,
        "feature_defaults": {
            feature: float(X[feature].mean())
            for feature in FEATURE_COLUMNS
        },
        "target": TARGET_COLUMN,
        "trained_date": date.today().isoformat()
    }
    with open(MODEL_INFO_PATH, "w", encoding="utf-8") as file:
        json.dump(model_info, file, indent=2)

    return {
        "status": "success",
        **model_info
    }

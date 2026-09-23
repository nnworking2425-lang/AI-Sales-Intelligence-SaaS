import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

import math


# ==========================
# LOAD DATA
# ==========================

data = pd.read_csv(
    "AI_SalesDataset_Orange.csv"
)


# ==========================
# FEATURES
# ==========================

features = [
    "OrderCount",
    "QuantitySold",
    "Revenue_Lag1",
    "Revenue_Lag2",
    "Revenue_Lag3",
    "Quantity_Lag1"
]


X = data[features]

y = data["ActualRevenue"]



# ==========================
# SPLIT DATA
# ==========================

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)



# ==========================
# LOAD MODEL
# ==========================

model = joblib.load(
    "model/random_forest_sales.pkl"
)



# ==========================
# TEST
# ==========================

prediction = model.predict(
    X_test
)



# ==========================
# SCORE
# ==========================

mae = mean_absolute_error(
    y_test,
    prediction
)


rmse = math.sqrt(
    mean_squared_error(
        y_test,
        prediction
    )
)


r2 = r2_score(
    y_test,
    prediction
)



print("\n===== AI MODEL VALIDATION =====")

print(
    f"Test Samples: {len(y_test)}"
)

print(
    f"MAE: {mae:.2f}"
)

print(
    f"RMSE: {rmse:.2f}"
)

print(
    f"R2 Score: {r2:.4f}"
)
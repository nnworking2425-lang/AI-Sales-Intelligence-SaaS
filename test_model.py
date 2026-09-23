import pandas as pd
import joblib
import math
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


# Load data
data = pd.read_csv("AI_SalesDataset_Orange.csv")


# Load model
model = joblib.load(
    "model/random_forest_sales.pkl"
)


# Lấy đúng các biến lúc train
features = [
    "OrderCount",
    "QuantitySold",
    "Revenue_Lag1",
    "Revenue_Lag2",
    "Revenue_Lag3",
    "Quantity_Lag1"
]


# Use the full dataset for evaluation
test_data = data


X_test = test_data[features]

y_true = test_data["ActualRevenue"]


# dự đoán
y_pred = model.predict(X_test)


# tạo bảng kết quả
result = pd.DataFrame({

    "Actual Revenue": y_true.values,

    "AI Prediction": y_pred,

    "Error": y_true.values - y_pred

})


print("\n===== TEST RESULT =====\n")

print(result)


mae = mean_absolute_error(
    y_true,
    y_pred
)

rmse = math.sqrt(
    mean_squared_error(
        y_true,
        y_pred
    )
)

r2 = r2_score(
    y_true,
    y_pred
)


print("\n===== FINAL MODEL SCORE =====")
print(f"MAE: {mae:.2f}")
print(f"RMSE: {rmse:.2f}")
print(f"R2 Score: {r2:.4f}")
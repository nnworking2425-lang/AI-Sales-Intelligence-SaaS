import pandas as pd
import joblib
from sklearn.ensemble import RandomForestRegressor

# đọc dữ liệu
data = pd.read_csv("AI_SalesDataset_Orange.csv")

# chọn biến đầu vào giống lúc bạn train trên Orange
X = data[
    [
        "OrderCount",
        "QuantitySold",
        "Revenue_Lag1",
        "Revenue_Lag2",
        "Revenue_Lag3",
        "Quantity_Lag1"
    ]
]

# biến cần dự đoán
y = data["ActualRevenue"]

# tạo model
model = RandomForestRegressor(
    n_estimators=100,
    random_state=42
)

# train
model.fit(X, y)

# lưu model
joblib.dump(
    model,
    "model/random_forest_sales.pkl"
)

print("Training completed!")
print("Model saved successfully!")
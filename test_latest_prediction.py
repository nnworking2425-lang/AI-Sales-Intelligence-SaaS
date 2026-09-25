import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "api"))

from app import app, DATABASE_PATH


def _ensure_seed_user(connection):
    user = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        ("dashboard-test-user",),
    ).fetchone()
    if user is None:
        connection.execute(
            """
            INSERT INTO users (username, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("dashboard-test-user", "dashboard@test.local", "hashed-password", "Viewer"),
        )
        connection.commit()
        return connection.execute(
            "SELECT id FROM users WHERE username = ?",
            ("dashboard-test-user",),
        ).fetchone()["id"]
    return user["id"]


def test_latest_prediction_and_dashboard_payload():
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("DELETE FROM prediction_history")
        user_id = _ensure_seed_user(connection)
        connection.execute(
            """
            INSERT INTO prediction_history (
                created_at, order_count, quantity_sold, revenue_lag1, revenue_lag2,
                revenue_lag3, quantity_lag1, actual_revenue, predicted_revenue
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-09-25 12:00:00",
                10,
                20,
                250.0,
                260.0,
                270.0,
                5,
                272.0,
                278.0,
            ),
        )
        connection.commit()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user_id"] = user_id
            session["auth_token"] = "test-token"

        latest_response = client.get("/api/latest-prediction")
        assert latest_response.status_code == 200, latest_response.get_data(as_text=True)
        latest_payload = latest_response.get_json()
        assert latest_payload["latest_forecast"] == 278.0, latest_payload
        assert latest_payload["predicted_revenue"] == 278.0, latest_payload

        dashboard_response = client.get("/api/dashboard")
        assert dashboard_response.status_code == 200, dashboard_response.get_data(as_text=True)
        dashboard_payload = dashboard_response.get_json()
        assert dashboard_payload["latest_forecast"] == 278.0, dashboard_payload


if __name__ == "__main__":
    test_latest_prediction_and_dashboard_payload()
    print("latest-prediction regression passed")

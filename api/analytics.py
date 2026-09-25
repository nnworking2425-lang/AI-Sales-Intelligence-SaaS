import json
import os

from flask import Blueprint, jsonify

try:
    from .database import get_connection
except ImportError:
    from database import get_connection
try:
    from .auth import login_required
except ImportError:
    from auth import login_required


analytics_bp = Blueprint("analytics", __name__)
DATABASE_PATH = None


def _read_model_metrics():
    model_info_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "model", "model_info.json"))
    try:
        if not os.path.exists(model_info_path):
            return {"r2": 0.0, "mae": 0.0, "rmse": 0.0, "test_samples": 0}
        with open(model_info_path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        return {
            "r2": float(payload.get("r2", 0) or 0),
            "mae": float(payload.get("mae", 0) or 0),
            "rmse": float(payload.get("rmse", 0) or 0),
            "test_samples": int(payload.get("samples", payload.get("test_samples", 0) or 0)),
        }
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return {"r2": 0.0, "mae": 0.0, "rmse": 0.0, "test_samples": 0}


def configure_analytics(database_path):
    global DATABASE_PATH
    DATABASE_PATH = database_path


def _rows(query):
    connection = get_connection(DATABASE_PATH)
    rows = connection.execute(query).fetchall()
    connection.close()
    return [dict(row) for row in rows]


@analytics_bp.get("/analytics")
@login_required
def analytics():
    connection = get_connection(DATABASE_PATH)
    totals = connection.execute("""
        SELECT
            COALESCE(SUM(actual_revenue), 0) AS total_revenue,
            COALESCE(AVG(actual_revenue), 0) AS average_revenue,
            COALESCE(MAX(actual_revenue), 0) AS highest_revenue
        FROM prediction_history
    """).fetchone()
    growth = connection.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN created_at >= date('now', '-7 day') THEN actual_revenue ELSE 0 END), 0) AS recent,
            COALESCE(SUM(CASE WHEN created_at < date('now', '-7 day') AND created_at >= date('now', '-14 day') THEN actual_revenue ELSE 0 END), 0) AS previous
        FROM prediction_history
    """).fetchone()
    best_day = connection.execute("""
        SELECT date(created_at) AS day, SUM(actual_revenue) AS revenue
        FROM prediction_history
        GROUP BY date(created_at)
        ORDER BY revenue DESC
        LIMIT 1
    """).fetchone()
    connection.close()

    previous = float(growth["previous"])
    recent = float(growth["recent"])
    growth_rate = ((recent - previous) / previous * 100) if previous else 0
    model_metrics = _read_model_metrics()
    return jsonify({
        "total_revenue": round(float(totals["total_revenue"]), 2),
        "average_revenue": round(float(totals["average_revenue"]), 2),
        "growth_rate": round(growth_rate, 2),
        "best_sales_day": best_day["day"] if best_day else None,
        "highest_revenue": round(float(totals["highest_revenue"]), 2),
        "r2": round(float(model_metrics["r2"]), 4),
        "mae": round(float(model_metrics["mae"]), 2),
        "rmse": round(float(model_metrics["rmse"]), 2),
        "test_samples": int(model_metrics["test_samples"]),
        "samples": int(model_metrics["test_samples"])
    })


@analytics_bp.get("/sales-trends")
@login_required
def sales_trends():
    return jsonify({
        "daily": _rows("""
            SELECT date(created_at) AS label, SUM(actual_revenue) AS revenue
            FROM prediction_history
            GROUP BY date(created_at)
            ORDER BY label
        """),
        "weekly": _rows("""
            SELECT strftime('%Y-W%W', created_at) AS label, SUM(actual_revenue) AS revenue
            FROM prediction_history
            GROUP BY strftime('%Y-W%W', created_at)
            ORDER BY label
        """),
        "monthly": _rows("""
            SELECT strftime('%Y-%m', created_at) AS label, SUM(actual_revenue) AS revenue
            FROM prediction_history
            GROUP BY strftime('%Y-%m', created_at)
            ORDER BY label
        """)
    })

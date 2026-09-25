import secrets
from functools import wraps
from datetime import datetime

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

try:
    from .database import get_connection
except ImportError:
    from database import get_connection


auth_bp = Blueprint("auth", __name__)
DATABASE_PATH = None
VALID_ROLES = {"Admin", "Sales", "Viewer"}


def configure_auth(database_path):
    global DATABASE_PATH
    DATABASE_PATH = database_path


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None

    connection = get_connection(DATABASE_PATH)
    user = connection.execute(
        "SELECT id, username, email, role, created_at FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    connection.close()
    return dict(user) if user else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = _current_user()
        if user is None:
            return jsonify({"error": "Authentication required."}), 401
        return view(*args, **kwargs)
    return wrapped


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = _current_user()
            if user is None:
                return jsonify({"error": "Authentication required."}), 401
            if user["role"] not in roles:
                return jsonify({"error": "You do not have permission for this action."}), 403
            return view(*args, **kwargs)
        return wrapped
    return decorator


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    role = str(payload.get("role", "Viewer")).strip().title()

    if not username or not email or len(password) < 8:
        return jsonify({"error": "Username, email, and an 8-character password are required."}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": "Role must be Admin, Sales, or Viewer."}), 400

    connection = get_connection(DATABASE_PATH)
    try:
        connection.execute(
            """
            INSERT INTO users(username, email, password_hash, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username, email, generate_password_hash(password), role, datetime.now().isoformat(timespec="seconds"))
        )
        connection.commit()
    except Exception as error:
        connection.close()
        if "UNIQUE" in str(error).upper():
            return jsonify({"error": "Username or email already exists."}), 409
        return jsonify({"error": "Unable to create user."}), 400
    connection.close()
    return jsonify({"status": "success", "message": "User registered successfully."}), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    username = str(payload.get("username", "") or "").strip()
    password = str(payload.get("password", "") or "")

    if not username or not password:
        return jsonify({
            "success": False,
            "message": "Invalid username or password"
        }), 401

    connection = get_connection(DATABASE_PATH)
    user = connection.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    connection.close()

    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify({
            "success": False,
            "message": "Invalid username or password"
        }), 401

    session.clear()
    session["user_id"] = user["id"]
    token = secrets.token_urlsafe(32)
    session["auth_token"] = token

    return jsonify({
        "success": True,
        "message": "Login successful",
        "token": token,
        "user": user["username"],
        "status": "success",
        "user_details": {
            "username": user["username"],
            "email": user["email"],
            "role": user["role"]
        }
    }), 200


@auth_bp.get("/current-user")
def current_user():
    user = _current_user()
    if user is None:
        return jsonify({"user": None}), 200
    return jsonify({"user": user})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"status": "success"})


@auth_bp.get("/users")
@roles_required("Admin")
def users():
    connection = get_connection(DATABASE_PATH)
    rows = connection.execute(
        "SELECT id, username, email, role, created_at FROM users ORDER BY id"
    ).fetchall()
    connection.close()
    return jsonify([dict(row) for row in rows])


@auth_bp.delete("/users/<int:user_id>")
@roles_required("Admin")
def delete_user(user_id):
    connection = get_connection(DATABASE_PATH)
    connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
    connection.commit()
    connection.close()
    return jsonify({"status": "success"})

import sqlite3


def get_connection(database_path):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path):
    connection = get_connection(database_path)
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Admin', 'Sales', 'Viewer')),
            created_at DATETIME NOT NULL
        );

        CREATE TABLE IF NOT EXISTS model_training_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_name TEXT,
            r2_score FLOAT,
            mae FLOAT,
            rmse FLOAT,
            created_at DATETIME
        );
    """)
    connection.commit()
    connection.close()

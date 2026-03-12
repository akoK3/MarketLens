import sqlite3
import os

DB_PATH = "marketlens.db"

# connecting Database SQL takes to the whole program
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            shares REAL NOT NULL,
            average_cost REAL NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS analysis_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            condition_type TEXT NOT NULL,
            threshold REAL NOT NULL,
            email TEXT,
            phone TEXT,
            triggered INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    
# Portfolio CRUD
def add_holding(ticker, shares, average_cost):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO portfolio (ticker, shares, average_cost) VALUES (?, ?, ?)",
        (ticker.upper(), shares, average_cost)
    )
    conn.commit()
    conn.close()

def get_portfolio():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM portfolio")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_holding(holding_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM portfolio WHERE id = ?", (holding_id,))
    conn.commit()
    conn.close()

# Analysis cache CRUD
def get_cached_analysis(ticker):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM analysis_cache WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1",
        (ticker.upper(),)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def save_analysis(ticker, analysis_json):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO analysis_cache (ticker, analysis_json) VALUES (?, ?)",
        (ticker.upper(), analysis_json)
    )
    conn.commit()
    conn.close()

# Alerts CRUD
def add_alert(ticker, condition_type, threshold, email=None, phone=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO alerts (ticker, condition_type, threshold, email, phone) VALUES (?, ?, ?, ?, ?)",
        (ticker.upper(), condition_type, threshold, email, phone)
    )
    conn.commit()
    conn.close()

def get_alerts(ticker=None):
    conn = get_connection()
    cursor = conn.cursor()
    if ticker:
        cursor.execute("SELECT * FROM alerts WHERE ticker = ? AND triggered = 0", (ticker.upper(),))
    else:
        cursor.execute("SELECT * FROM alerts WHERE triggered = 0")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def mark_alert_triggered(alert_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE alerts SET triggered = 1 WHERE id = ?", (alert_id,))
    conn.commit()
    conn.close()
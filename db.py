import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "prenos.db"

def get_connection():
    """Returns a SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database tables if they do not exist."""
    with get_connection() as conn:
        # Create posts table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                original_content TEXT NOT NULL,
                final_content TEXT,
                status TEXT NOT NULL,
                llm_provider TEXT,
                llm_model TEXT,
                event_id TEXT,
                relay_results TEXT,
                conversation_history TEXT,
                llm_metadata TEXT
            )
        """)
        
        # Create settings table for key-value storage
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        conn.commit()

# --- Settings Helper Functions ---

def save_setting(key: str, value: any):
    """Saves a setting key-value pair. Values are JSON serialized."""
    init_db()
    with get_connection() as conn:
        val_str = json.dumps(value)
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, val_str)
        )
        conn.commit()

def get_setting(key: str, default: any = None) -> any:
    """Retrieves a setting value. Deserializes from JSON."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return row["value"]
        return default

# --- Posts Helper Functions ---

def create_post(original_content: str, status: str = "draft", llm_provider: str = None, llm_model: str = None) -> int:
    """Creates a new post entry and returns the auto-generated post ID."""
    init_db()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO posts (
                created_at, original_content, status, llm_provider, llm_model, 
                conversation_history, relay_results, llm_metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (now_str, original_content, status, llm_provider, llm_model, 
             json.dumps([]), json.dumps({}), json.dumps({}))
        )
        conn.commit()
        return cursor.lastrowid

def update_post(
    post_id: int,
    status: str = None,
    final_content: str = None,
    event_id: str = None,
    relay_results: dict = None,
    conversation_history: list = None,
    llm_metadata: dict = None,
    llm_provider: str = None,
    llm_model: str = None
):
    """Updates fields of a specific post."""
    init_db()
    updates = []
    params = []
    
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if final_content is not None:
        updates.append("final_content = ?")
        params.append(final_content)
    if event_id is not None:
        updates.append("event_id = ?")
        params.append(event_id)
    if relay_results is not None:
        updates.append("relay_results = ?")
        params.append(json.dumps(relay_results))
    if conversation_history is not None:
        updates.append("conversation_history = ?")
        params.append(json.dumps(conversation_history))
    if llm_metadata is not None:
        updates.append("llm_metadata = ?")
        params.append(json.dumps(llm_metadata))
    if llm_provider is not None:
        updates.append("llm_provider = ?")
        params.append(llm_provider)
    if llm_model is not None:
        updates.append("llm_model = ?")
        params.append(llm_model)
        
    if not updates:
        return
        
    params.append(post_id)
    query = f"UPDATE posts SET {', '.join(updates)} WHERE id = ?"
    
    with get_connection() as conn:
        conn.execute(query, tuple(params))
        conn.commit()

def get_post(post_id: int) -> dict:
    """Retrieves a single post by ID, deserializing JSON fields."""
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if row:
            res = dict(row)
            try:
                res["conversation_history"] = json.loads(res["conversation_history"]) if res["conversation_history"] else []
            except Exception:
                res["conversation_history"] = []
            try:
                res["relay_results"] = json.loads(res["relay_results"]) if res["relay_results"] else {}
            except Exception:
                res["relay_results"] = {}
            try:
                res["llm_metadata"] = json.loads(res["llm_metadata"]) if res["llm_metadata"] else {}
            except Exception:
                res["llm_metadata"] = {}
            return res
        return None

def get_all_posts(limit: int = 50) -> list:
    """Retrieves all posts sorted by creation date descending."""
    init_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        posts = []
        for r in rows:
            res = dict(r)
            try:
                res["conversation_history"] = json.loads(res["conversation_history"]) if res["conversation_history"] else []
            except Exception:
                res["conversation_history"] = []
            try:
                res["relay_results"] = json.loads(res["relay_results"]) if res["relay_results"] else {}
            except Exception:
                res["relay_results"] = {}
            try:
                res["llm_metadata"] = json.loads(res["llm_metadata"]) if res["llm_metadata"] else {}
            except Exception:
                res["llm_metadata"] = {}
            posts.append(res)
        return posts

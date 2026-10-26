import sqlite3
import csv
import json
import sys
from pathlib import Path
from datetime import datetime

APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
ENV_PATH = APP_DIR / ".env"
RECORDINGS_DIR = APP_DIR / "recordings"
DB_PATH = APP_DIR / "assistant_history.db"


def resolve_audio_path(value):
    if not value:
        return None
    original = Path(value)
    for candidate in (RECORDINGS_DIR / original.name, APP_DIR / original, original):
        if candidate.is_file():
            return candidate
    return None


class SessionDatabase:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    transcript TEXT NOT NULL,
                    response TEXT NOT NULL,
                    tool_called TEXT,
                    audio_path TEXT,
                    latency_sec REAL
                )
            """)
            conn.commit()

    def add_record(self, session_id, transcript, response, tool_called=None, audio_path=None, latency_sec=0.0):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stored_audio = ""
        if audio_path:
            path = Path(audio_path)
            try:
                stored_audio = str(path.resolve().relative_to(APP_DIR))
            except ValueError:
                stored_audio = str(path)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (timestamp, session_id, transcript, response, tool_called, audio_path, latency_sec)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, session_id, transcript, response, tool_called or "None", stored_audio, round(latency_sec, 2)))
            conn.commit()
            return cursor.lastrowid

    def get_all_records(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def clear_history(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions")
            conn.commit()

    def export_to_csv(self, filepath):
        records = self.get_all_records()
        if not records:
            return False
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
        return True

    def export_to_json(self, filepath):
        records = self.get_all_records()
        if not records:
            return False
        with open(filepath, mode="w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
        return True

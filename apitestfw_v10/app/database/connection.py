"""
app/database/connection.py — Thin connection pool helpers.
Each function opens a fresh connection and closes it on exit.
"""
import pymysql
from config import Config


def get_conn():
    """Return a new raw PyMySQL connection."""
    return pymysql.connect(**Config.db_cfg())


def execute(sql: str, params=None) -> int:
    """Run INSERT / UPDATE / DELETE. Returns lastrowid."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            lid = cur.lastrowid
        conn.commit()
        return lid
    finally:
        conn.close()


def query(sql: str, params=None) -> list:
    """Run SELECT. Returns list of dicts."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql: str, params=None) -> dict | None:
    """Run SELECT. Returns single dict or None."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.fetchone()
    finally:
        conn.close()

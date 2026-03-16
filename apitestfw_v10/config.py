"""
config.py — Central configuration. All settings come from .env file.
Copy .env.example → .env and fill in your values.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY         = os.environ.get("SECRET_KEY", "change-me-in-production-xyz987")
    DB_HOST            = os.environ.get("DB_HOST", "localhost")
    DB_PORT            = int(os.environ.get("DB_PORT", 3306))
    DB_USER            = os.environ.get("DB_USER", "root")
    DB_PASS            = os.environ.get("DB_PASS", "")
    DB_NAME            = os.environ.get("DB_NAME", "apitestfw")
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024   # 32 MB upload limit

    @classmethod
    def db_cfg(cls) -> dict:
        import pymysql
        return dict(
            host        = cls.DB_HOST,
            port        = cls.DB_PORT,
            user        = cls.DB_USER,
            password    = cls.DB_PASS,
            database    = cls.DB_NAME,
            charset     = "utf8mb4",
            cursorclass = pymysql.cursors.DictCursor,
            autocommit  = False,
        )

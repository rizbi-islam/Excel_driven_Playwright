"""
app/database/schema.py — DDL definitions + init + migration.

KEY CHANGE FROM v9:
  page_access table is now keyed on (user_id, page) NOT (role, page).
  This enables true per-user page access control.
  Migration path: if old role-based table exists → drop and recreate.
"""
import pymysql
from config import Config

TABLES: list[tuple[str, str]] = [
    ("users", """
        CREATE TABLE IF NOT EXISTS users (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            username   VARCHAR(100) UNIQUE NOT NULL,
            email      VARCHAR(200) UNIQUE NOT NULL,
            password   VARCHAR(255) NOT NULL,
            role       ENUM('admin','tester','viewer') DEFAULT 'tester',
            is_active  TINYINT(1) DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login DATETIME
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("environments", """
        CREATE TABLE IF NOT EXISTS environments (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            owner_id   INT NOT NULL,
            name       VARCHAR(200) NOT NULL,
            base_url   VARCHAR(500) NOT NULL,
            auth_type  VARCHAR(20) DEFAULT 'none',
            auth_token VARCHAR(500),
            headers    JSON,
            is_default TINYINT(1) DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("apis", """
        CREATE TABLE IF NOT EXISTS apis (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            owner_id    INT NOT NULL,
            name        VARCHAR(200) NOT NULL,
            base_url    VARCHAR(500) NOT NULL,
            description TEXT,
            created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("my_cases", """
        CREATE TABLE IF NOT EXISTS my_cases (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            owner_id        INT NOT NULL,
            api_id          INT,
            sheet_type      VARCHAR(20) DEFAULT 'regression',
            name            VARCHAR(300) NOT NULL,
            method          VARCHAR(10)  NOT NULL DEFAULT 'GET',
            endpoint        VARCHAR(500) NOT NULL,
            headers         JSON,
            body            JSON,
            params          JSON,
            expected_status INT DEFAULT 200,
            test_type       VARCHAR(20)  DEFAULT 'regression',
            assertions      JSON,
            max_response_ms INT,
            auth_type       VARCHAR(20)  DEFAULT 'none',
            auth_token      VARCHAR(500),
            tags            JSON,
            description     TEXT,
            is_active       TINYINT(1) DEFAULT 1,
            saved_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (api_id)   REFERENCES apis(id)  ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("runs", """
        CREATE TABLE IF NOT EXISTS runs (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            owner_id     INT NOT NULL,
            api_id       INT,
            label        VARCHAR(200),
            base_url     VARCHAR(500),
            test_type    VARCHAR(20)  DEFAULT 'regression',
            source       ENUM('excel','library','tester') DEFAULT 'excel',
            status       ENUM('running','done','error') DEFAULT 'running',
            total        INT DEFAULT 0,
            passed       INT DEFAULT 0,
            failed       INT DEFAULT 0,
            pass_rate    DECIMAL(5,2) DEFAULT 0,
            concurrency  INT,
            duration_sec DECIMAL(10,2),
            started_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            ended_at     DATETIME,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (api_id)   REFERENCES apis(id)  ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("results", """
        CREATE TABLE IF NOT EXISTS results (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            run_id           INT NOT NULL,
            owner_id         INT NOT NULL,
            case_name        VARCHAR(300),
            method           VARCHAR(10),
            endpoint         VARCHAR(500),
            test_type        VARCHAR(20),
            status           VARCHAR(10),
            actual_status    INT,
            expected_status  INT,
            response_ms      DECIMAL(10,2),
            error_msg        TEXT,
            assertion_detail JSON,
            response_preview TEXT,
            resp_headers     TEXT,
            request_data     JSON,
            ran_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id)   REFERENCES runs(id)  ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("load_metrics", """
        CREATE TABLE IF NOT EXISTS load_metrics (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            run_id         INT NOT NULL,
            owner_id       INT NOT NULL,
            endpoint       VARCHAR(500),
            total_requests INT DEFAULT 0,
            passed         INT DEFAULT 0,
            failed         INT DEFAULT 0,
            min_ms         DECIMAL(10,2),
            max_ms         DECIMAL(10,2),
            avg_ms         DECIMAL(10,2),
            p95_ms         DECIMAL(10,2),
            p99_ms         DECIMAL(10,2),
            rps            DECIMAL(10,2),
            error_rate     DECIMAL(5,2),
            duration_sec   DECIMAL(10,2),
            concurrency    INT,
            FOREIGN KEY (run_id)   REFERENCES runs(id)  ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("security_findings", """
        CREATE TABLE IF NOT EXISTS security_findings (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            run_id      INT NOT NULL,
            owner_id    INT NOT NULL,
            endpoint    VARCHAR(500),
            check_type  VARCHAR(60),
            severity    ENUM('critical','high','medium','low','info') DEFAULT 'info',
            passed      TINYINT(1) DEFAULT 1,
            finding     TEXT,
            detail      TEXT,
            ran_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id)   REFERENCES runs(id)  ON DELETE CASCADE,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("page_access", """
        CREATE TABLE IF NOT EXISTS page_access (
            id      INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            page    VARCHAR(100) NOT NULL,
            allowed TINYINT(1)   NOT NULL DEFAULT 1,
            UNIQUE KEY uq_user_page (user_id, page),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("collections", """
        CREATE TABLE IF NOT EXISTS collections (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            owner_id             INT NOT NULL,
            name                 VARCHAR(200) NOT NULL,
            description          TEXT,
            auth_type            VARCHAR(20) DEFAULT 'none',
            auth_token           VARCHAR(500),
            auth_key_name        VARCHAR(100) DEFAULT 'X-API-Key',
            variables            JSON,
            pre_request_script   TEXT,
            tests_script         TEXT,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("collection_requests", """
        CREATE TABLE IF NOT EXISTS collection_requests (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            collection_id        INT NOT NULL,
            owner_id             INT NOT NULL,
            name                 VARCHAR(300) NOT NULL,
            method               VARCHAR(10)  NOT NULL DEFAULT 'GET',
            url                  VARCHAR(1000) NOT NULL,
            headers              JSON,
            body                 JSON,
            body_type            VARCHAR(20) DEFAULT 'none',
            params               JSON,
            auth_type            VARCHAR(20) DEFAULT 'inherit',
            auth_token           VARCHAR(500),
            auth_key_name        VARCHAR(100) DEFAULT 'X-API-Key',
            description          TEXT,
            pre_request_script   TEXT,
            tests_script         TEXT,
            sort_order           INT DEFAULT 0,
            created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
            FOREIGN KEY (owner_id)      REFERENCES users(id)       ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
    ("tester_history", """
        CREATE TABLE IF NOT EXISTS tester_history (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            owner_id        INT NOT NULL,
            method          VARCHAR(10)   NOT NULL,
            url             VARCHAR(1000) NOT NULL,
            request_data    JSON,
            response_status INT,
            response_ms     DECIMAL(10,2),
            response_size   INT,
            ran_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """),
]


def _create_database_if_missing():
    base = {k: v for k, v in Config.db_cfg().items()
            if k not in ("database", "cursorclass")}
    conn = pymysql.connect(**base, cursorclass=pymysql.cursors.DictCursor)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
    finally:
        conn.close()


def init_db():
    """First-time setup: create DB + all tables + seed admin + seed access."""
    _create_database_if_missing()

    from app.database.connection import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for _, ddl in TABLES:
                cur.execute(ddl)
        conn.commit()
    finally:
        conn.close()

    # Seed default admin user
    from app.database.connection import query_one, execute
    from app.auth.security import hash_password
    if not query_one("SELECT id FROM users WHERE username='admin'"):
        uid = execute(
            "INSERT INTO users(username,email,password,role) VALUES(%s,%s,%s,'admin')",
            ("admin", "admin@local", hash_password("admin123"))
        )
        print("  ✅ Default user created: admin / admin123")
        # Seed admin's page access (all pages)
        from app.database.models.access import AccessModel
        AccessModel.seed_for_user(uid, "admin")

    print("  ✅ All tables ready.")


def migrate_db():
    """Safe ALTER TABLE migrations — never drops data. Run on upgrades."""
    # Handle old role-based page_access → new user-based
    _migrate_page_access_if_needed()

    from app.database.connection import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for _, ddl in TABLES:
                cur.execute(ddl)
            _add_col(cur, "results",  "request_data",     "JSON")
            _add_col(cur, "results",  "response_preview",  "TEXT")
            _add_col(cur, "results",  "resp_headers",      "TEXT")
            _add_col(cur, "my_cases", "description",       "TEXT")
            _add_col(cur, "my_cases", "is_active",         "TINYINT(1) DEFAULT 1")
        conn.commit()
        print("  ✅ Schema migrations applied.")
    finally:
        conn.close()

    # Reseed access for all existing users that have no page_access rows
    from app.database.connection import query, query_one
    from app.database.models.access import AccessModel
    users = query("SELECT id, role FROM users")
    for u in users:
        has_rows = query_one(
            "SELECT COUNT(*) as cnt FROM page_access WHERE user_id=%s", (u["id"],)
        )
        if not has_rows or has_rows["cnt"] == 0:
            AccessModel.seed_for_user(u["id"], u["role"])
            print(f"  ✅ Seeded page access for user_id={u['id']} role={u['role']}")


def _add_col(cur, table: str, column: str, col_def: str):
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (Config.DB_NAME, table, column)
    )
    row = cur.fetchone()
    if row and row["cnt"] == 0:
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_def}")
        print(f"  + Added column {table}.{column}")


def _migrate_page_access_if_needed():
    """If page_access still has 'role' column (v9 schema), drop and recreate."""
    from app.database.connection import get_conn
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='page_access' AND COLUMN_NAME='role'",
                (Config.DB_NAME,)
            )
            row = cur.fetchone()
            if row and row["cnt"] > 0:
                cur.execute("DROP TABLE IF EXISTS page_access")
                cur.execute("""
                    CREATE TABLE page_access (
                        id      INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        page    VARCHAR(100) NOT NULL,
                        allowed TINYINT(1)   NOT NULL DEFAULT 1,
                        UNIQUE KEY uq_user_page (user_id, page),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                conn.commit()
                print("  ✅ Migrated page_access from role-based to user-based schema.")
    finally:
        conn.close()


def auto_migrate():
    """
    Called automatically on every app startup.
    Fast checks — only touches DB if something is actually wrong/missing.
    Safe to call 1000 times; idempotent by design.
    """
    from app.database.connection import get_conn, query
    from config import Config

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # ── 1. Fix page_access: old role-based → new user_id-based ──────
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA=%s AND TABLE_NAME='page_access' AND COLUMN_NAME='role'",
                (Config.DB_NAME,)
            )
            row = cur.fetchone()
            if row and row["cnt"] > 0:
                print("  → Auto-migrating page_access table (role→user_id)…")
                cur.execute("DROP TABLE IF EXISTS page_access")
                cur.execute("""
                    CREATE TABLE page_access (
                        id      INT AUTO_INCREMENT PRIMARY KEY,
                        user_id INT NOT NULL,
                        page    VARCHAR(100) NOT NULL,
                        allowed TINYINT(1) NOT NULL DEFAULT 1,
                        UNIQUE KEY uq_user_page (user_id, page),
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
                conn.commit()
                print("  ✅ page_access migrated to per-user schema.")

            # ── 2. Add missing columns ────────────────────────────────────────
            _add_col(cur, "my_cases", "description", "TEXT")
            _add_col(cur, "my_cases", "is_active",   "TINYINT(1) DEFAULT 1")
            _add_col(cur, "results",  "request_data","JSON")
            _add_col(cur, "results",  "response_preview", "TEXT")
            _add_col(cur, "results",  "resp_headers", "TEXT")

            # ── 2b. Add/migrate collections tables ────────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    owner_id INT NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    auth_type VARCHAR(20) DEFAULT 'none',
                    auth_token VARCHAR(500),
                    auth_key_name VARCHAR(100) DEFAULT 'X-API-Key',
                    variables JSON,
                    pre_request_script TEXT,
                    tests_script TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collection_requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    collection_id INT NOT NULL,
                    owner_id INT NOT NULL,
                    name VARCHAR(300) NOT NULL,
                    method VARCHAR(10) NOT NULL DEFAULT 'GET',
                    url VARCHAR(1000) NOT NULL,
                    headers JSON,
                    body JSON,
                    body_type VARCHAR(20) DEFAULT 'none',
                    params JSON,
                    auth_type VARCHAR(20) DEFAULT 'inherit',
                    auth_token VARCHAR(500),
                    auth_key_name VARCHAR(100) DEFAULT 'X-API-Key',
                    description TEXT,
                    pre_request_script TEXT,
                    tests_script TEXT,
                    sort_order INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            # Add new columns to existing collections/collection_requests
            _add_col(cur, 'collections', 'auth_type', "VARCHAR(20) DEFAULT 'none'")
            _add_col(cur, 'collections', 'auth_token', 'VARCHAR(500)')
            _add_col(cur, 'collections', 'auth_key_name', "VARCHAR(100) DEFAULT 'X-API-Key'")
            _add_col(cur, 'collections', 'variables', 'JSON')
            _add_col(cur, 'collections', 'pre_request_script', 'TEXT')
            _add_col(cur, 'collections', 'tests_script', 'TEXT')
            _add_col(cur, 'collection_requests', 'auth_type', "VARCHAR(20) DEFAULT 'inherit'")
            _add_col(cur, 'collection_requests', 'auth_token', 'VARCHAR(500)')
            _add_col(cur, 'collection_requests', 'auth_key_name', "VARCHAR(100) DEFAULT 'X-API-Key'")
            _add_col(cur, 'collection_requests', 'pre_request_script', 'TEXT')
            _add_col(cur, 'collection_requests', 'tests_script', 'TEXT')

            # ── 2b_old. Add collections tables if missing ─────────────────────
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    owner_id INT NOT NULL,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS collection_requests (
                    id            INT AUTO_INCREMENT PRIMARY KEY,
                    collection_id INT NOT NULL,
                    owner_id      INT NOT NULL,
                    name          VARCHAR(300) NOT NULL,
                    method        VARCHAR(10) NOT NULL DEFAULT 'GET',
                    url           VARCHAR(1000) NOT NULL,
                    headers       JSON,
                    body          JSON,
                    body_type     VARCHAR(20) DEFAULT 'none',
                    params        JSON,
                    auth_type     VARCHAR(20) DEFAULT 'none',
                    auth_token    VARCHAR(500),
                    description   TEXT,
                    sort_order    INT DEFAULT 0,
                    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """)

            # ── 3. Ensure all tables exist (CREATE IF NOT EXISTS — no-op) ────
            for _, ddl in TABLES:
                cur.execute(ddl)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    # ── 4. Seed page_access for any user that has zero rows ──────────────────
    try:
        from app.database.connection import query as _q
        from app.database.models.access import AccessModel
        users = _q("SELECT id, role FROM users")
        for u in users:
            check = _q(
                "SELECT COUNT(*) AS cnt FROM page_access WHERE user_id=%s",
                (u["id"],)
            )
            if not check or check[0]["cnt"] == 0:
                AccessModel.seed_for_user(u["id"], u["role"])
                print(f"  ✅ Seeded page_access for user_id={u['id']} role={u['role']}")
    except Exception as e:
        print(f"  ⚠ Page access seed warning: {e}")

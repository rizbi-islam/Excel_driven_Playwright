"""
app/database/models/access.py — Per-USER page access control.

Architecture (KEY FIX from v9):
  - Table: page_access(user_id, page, allowed)  — NOT (role, page)
  - Admin users always pass in the decorator without a DB query.
  - When a new user is created → seed rows from their role's defaults.
  - Admin can later toggle individual user+page cells independently.
  - Role change → reset all that user's rows to new role's defaults.
"""
from app.database.connection import execute, query, query_one

# All navigable pages: (key, label, route)
ALL_PAGES: list[tuple[str, str, str]] = [
    ("dashboard",  "Dashboard",        "/"),
    ("tester",     "API Tester",       "/tester"),
    ("generate",   "Auto-Generate",    "/generate"),
    ("smoke",      "Smoke Tests",      "/run/smoke"),
    ("regression", "Regression Tests", "/run/regression"),
    ("load",       "Load Tests",       "/run/load"),
    ("stress",     "Stress Tests",     "/run/stress"),
    ("security",   "Security Scan",    "/run/security"),
    ("library",    "Saved Cases",      "/library"),
    ("history",    "Run History",      "/history"),
    ("envs",       "Environments",     "/envs"),
    ("apis",       "My APIs",          "/apis"),
    ("users",      "User Management",  "/users"),
    ("access",     "Page Access",      "/access"),
]

# Role defaults — used ONLY for seeding new users. Not for live checks.
ROLE_DEFAULTS: dict[str, set] = {
    "admin":  {p[0] for p in ALL_PAGES},
    "tester": {
        "dashboard", "tester", "generate", "smoke", "regression",
        "load", "stress", "security", "library", "history", "envs", "apis",
    },
    "viewer": {"dashboard", "history", "library"},
}


class AccessModel:

    @staticmethod
    def seed_for_user(user_id: int, role: str) -> None:
        """
        Insert page_access rows for a user based on their role's defaults.
        Safe to call repeatedly — uses ON DUPLICATE KEY UPDATE.
        Called when: user created, role changed, admin resets a user.
        """
        defaults = ROLE_DEFAULTS.get(role, set())
        for page_key, _, _ in ALL_PAGES:
            allowed = 1 if page_key in defaults else 0
            execute(
                "INSERT INTO page_access(user_id, page, allowed) VALUES(%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE allowed=VALUES(allowed)",
                (user_id, page_key, allowed)
            )

    @staticmethod
    def user_can(user_id: int, page_key: str) -> bool:
        """
        Check if a specific user can access a specific page.
        Falls back to role-based defaults if no DB rows exist yet (e.g. first login).
        """
        row = query_one(
            "SELECT allowed FROM page_access WHERE user_id=%s AND page=%s",
            (user_id, page_key)
        )
        if row is not None:
            return bool(row["allowed"])
        # No rows yet — check if any rows exist for this user at all
        has_any = query_one(
            "SELECT COUNT(*) AS cnt FROM page_access WHERE user_id=%s", (user_id,)
        )
        if has_any and has_any["cnt"] == 0:
            # Never seeded — seed now from role, then re-check
            from app.database.models.user import UserModel
            user = UserModel.find_by_id(user_id)
            if user:
                AccessModel.seed_for_user(user_id, user["role"])
                row2 = query_one(
                    "SELECT allowed FROM page_access WHERE user_id=%s AND page=%s",
                    (user_id, page_key)
                )
                return bool(row2["allowed"]) if row2 else False
        return False

    @staticmethod
    def get_for_user(user_id: int) -> dict[str, bool]:
        """Returns {page_key: allowed_bool} for a single user."""
        rows = query(
            "SELECT page, allowed FROM page_access WHERE user_id=%s",
            (user_id,)
        )
        return {r["page"]: bool(r["allowed"]) for r in rows}

    @staticmethod
    def get_all_matrix() -> dict[int, dict[str, bool]]:
        """
        Returns {user_id: {page_key: allowed_bool}} for the admin access grid.
        """
        rows = query(
            "SELECT user_id, page, allowed FROM page_access ORDER BY user_id, page"
        )
        result: dict[int, dict[str, bool]] = {}
        for row in rows:
            result.setdefault(row["user_id"], {})[row["page"]] = bool(row["allowed"])
        return result

    @staticmethod
    def save_user_matrix(user_id: int, pages: dict[str, bool]) -> int:
        """
        Upsert all page rows for one user atomically.
        pages = {"dashboard": True, "tester": False, ...}
        Returns count of rows written.
        """
        from app.database.connection import get_conn
        valid = {p[0] for p in ALL_PAGES}
        conn  = get_conn()
        count = 0
        try:
            with conn.cursor() as cur:
                for page, allowed in pages.items():
                    if page in valid:
                        cur.execute(
                            "INSERT INTO page_access(user_id,page,allowed) VALUES(%s,%s,%s) "
                            "ON DUPLICATE KEY UPDATE allowed=%s",
                            (user_id, page, int(bool(allowed)), int(bool(allowed)))
                        )
                        count += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return count

    @staticmethod
    def reset_to_role(user_id: int, role: str) -> None:
        """Reset a user's page access to the defaults for the given role."""
        AccessModel.seed_for_user(user_id, role)

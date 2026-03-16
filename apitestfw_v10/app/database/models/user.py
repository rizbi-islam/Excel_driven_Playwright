"""app/database/models/user.py — User entity."""
from app.database.connection import execute, query, query_one


class UserModel:

    @staticmethod
    def find_by_id(uid: int) -> dict | None:
        return query_one("SELECT * FROM users WHERE id=%s", (uid,))

    @staticmethod
    def find_by_username(username: str) -> dict | None:
        return query_one("SELECT * FROM users WHERE username=%s", (username,))

    @staticmethod
    def all() -> list:
        return query(
            "SELECT id,username,email,role,is_active,created_at,last_login "
            "FROM users ORDER BY id"
        )

    @staticmethod
    def create(username: str, email: str, password: str, role: str) -> int:
        return execute(
            "INSERT INTO users(username,email,password,role) VALUES(%s,%s,%s,%s)",
            (username, email, password, role)
        )

    @staticmethod
    def update_last_login(uid: int) -> None:
        execute("UPDATE users SET last_login=NOW() WHERE id=%s", (uid,))

    @staticmethod
    def toggle_active(uid: int) -> None:
        execute("UPDATE users SET is_active = NOT is_active WHERE id=%s", (uid,))

    @staticmethod
    def update_role(uid: int, role: str) -> None:
        execute("UPDATE users SET role=%s WHERE id=%s", (role, uid))

    @staticmethod
    def update_password(uid: int, hashed: str) -> None:
        execute("UPDATE users SET password=%s WHERE id=%s", (hashed, uid))

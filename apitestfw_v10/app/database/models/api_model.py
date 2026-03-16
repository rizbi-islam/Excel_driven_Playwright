"""app/database/models/api_model.py — API entity."""
from app.database.connection import execute, query, query_one


class ApiModel:

    @staticmethod
    def all_for_user(owner_id: int) -> list:
        return query(
            "SELECT * FROM apis WHERE owner_id=%s ORDER BY created_at DESC",
            (owner_id,)
        )

    @staticmethod
    def get(api_id: int, owner_id: int) -> dict | None:
        return query_one(
            "SELECT * FROM apis WHERE id=%s AND owner_id=%s",
            (api_id, owner_id)
        )

    @staticmethod
    def create(owner_id: int, name: str, base_url: str, description: str = "") -> int:
        return execute(
            "INSERT INTO apis(owner_id,name,base_url,description) VALUES(%s,%s,%s,%s)",
            (owner_id, name, base_url, description)
        )

    @staticmethod
    def delete(api_id: int, owner_id: int) -> None:
        execute("DELETE FROM apis WHERE id=%s AND owner_id=%s", (api_id, owner_id))

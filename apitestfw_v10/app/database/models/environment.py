"""app/database/models/environment.py — Environment entity."""
import json
from app.database.connection import execute, query, query_one


def _j(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v


class EnvironmentModel:

    @staticmethod
    def all_for_user(owner_id: int) -> list:
        return query(
            "SELECT * FROM environments WHERE owner_id=%s ORDER BY is_default DESC, name",
            (owner_id,)
        )

    @staticmethod
    def get(env_id: int, owner_id: int) -> dict | None:
        return query_one(
            "SELECT * FROM environments WHERE id=%s AND owner_id=%s",
            (env_id, owner_id)
        )

    @staticmethod
    def create(owner_id: int, data: dict) -> int:
        return execute(
            "INSERT INTO environments(owner_id,name,base_url,auth_type,auth_token,headers,is_default) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (
                owner_id,
                data["name"],
                data["base_url"],
                data.get("auth_type", "none"),
                data.get("auth_token", ""),
                _j(data.get("headers", {})),
                1 if data.get("is_default") else 0,
            )
        )

    @staticmethod
    def set_default(env_id: int, owner_id: int) -> None:
        execute("UPDATE environments SET is_default=0 WHERE owner_id=%s", (owner_id,))
        execute(
            "UPDATE environments SET is_default=1 WHERE id=%s AND owner_id=%s",
            (env_id, owner_id)
        )

    @staticmethod
    def delete(env_id: int, owner_id: int) -> None:
        execute(
            "DELETE FROM environments WHERE id=%s AND owner_id=%s",
            (env_id, owner_id)
        )

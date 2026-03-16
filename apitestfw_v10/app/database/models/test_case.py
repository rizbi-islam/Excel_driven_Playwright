"""app/database/models/test_case.py — Test Case (library) entity."""
import json
from app.database.connection import execute, query, query_one


def _j(v):
    if v is None:
        return None
    return json.dumps(v) if isinstance(v, (dict, list)) else v


class TestCaseModel:

    @staticmethod
    def all_for_user(owner_id: int, api_id: int = None, sheet_type: str = None) -> list:
        where  = ["c.owner_id=%s"]
        params = [owner_id]
        if api_id:
            where.append("c.api_id=%s")
            params.append(api_id)
        if sheet_type:
            where.append("c.sheet_type=%s")
            params.append(sheet_type)
        return query(
            f"SELECT c.*, a.name AS api_name FROM my_cases c "
            f"LEFT JOIN apis a ON c.api_id=a.id "
            f"WHERE {' AND '.join(where)} ORDER BY c.saved_at DESC",
            params
        )

    @staticmethod
    def get(case_id: int, owner_id: int) -> dict | None:
        return query_one(
            "SELECT * FROM my_cases WHERE id=%s AND owner_id=%s",
            (case_id, owner_id)
        )

    @staticmethod
    def save(owner_id: int, data: dict) -> int:
        return execute(
            "INSERT INTO my_cases("
            "  owner_id,api_id,sheet_type,name,method,endpoint,"
            "  headers,body,params,expected_status,test_type,assertions,"
            "  max_response_ms,auth_type,auth_token,tags,description,is_active,"
            "  pre_request_script,tests_script"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                owner_id,
                data.get("api_id"),
                data.get("sheet_type", "regression"),
                data["name"],
                data.get("method", "GET"),
                data["endpoint"],
                _j(data.get("headers", {})),
                _j(data.get("body")),
                _j(data.get("params", {})),
                data.get("expected_status", 200),
                data.get("test_type", "regression"),
                _j(data.get("assertions", [])),
                data.get("max_response_ms"),
                data.get("auth_type", "none"),
                data.get("auth_token", ""),
                _j(data.get("tags", [])),
                data.get("description", ""),
                1 if data.get("is_active", True) else 0,
                data.get("pre_request_script", ""),
                data.get("tests_script", ""),
            )
        )

    @staticmethod
    def toggle_active(case_id: int, owner_id: int) -> bool:
        """Toggle is_active. Returns new state."""
        row = query_one(
            "SELECT is_active FROM my_cases WHERE id=%s AND owner_id=%s",
            (case_id, owner_id)
        )
        if not row:
            return False
        new_val = 0 if row["is_active"] else 1
        execute(
            "UPDATE my_cases SET is_active=%s WHERE id=%s AND owner_id=%s",
            (new_val, case_id, owner_id)
        )
        return bool(new_val)

    @staticmethod
    def bulk_save(owner_id: int, cases: list, api_id: int = None) -> int:
        saved = 0
        for case in cases:
            case["api_id"] = api_id
            try:
                TestCaseModel.save(owner_id, case)
                saved += 1
            except Exception:
                pass
        return saved

    @staticmethod
    def delete(case_id: int, owner_id: int) -> None:
        execute(
            "DELETE FROM my_cases WHERE id=%s AND owner_id=%s",
            (case_id, owner_id)
        )

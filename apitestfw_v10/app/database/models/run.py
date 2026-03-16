"""app/database/models/run.py — Run, Result, LoadMetric, SecurityFinding, Stats entities."""
import json
from app.database.connection import execute, query, query_one


def _j(v):
    if v is None:
        return None
    return json.dumps(v) if isinstance(v, (dict, list)) else v


class RunModel:

    @staticmethod
    def create(owner_id, api_id, label, base_url, test_type,
               source="excel", concurrency=None) -> int:
        return execute(
            "INSERT INTO runs(owner_id,api_id,label,base_url,test_type,source,concurrency) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s)",
            (owner_id, api_id, label, base_url, test_type, source, concurrency)
        )

    @staticmethod
    def finish(run_id, total, passed, failed, duration=None) -> None:
        rate = round(passed / total * 100, 1) if total else 0
        execute(
            "UPDATE runs SET status='done',total=%s,passed=%s,failed=%s,"
            "pass_rate=%s,duration_sec=%s,ended_at=NOW() WHERE id=%s",
            (total, passed, failed, rate, duration, run_id)
        )

    @staticmethod
    def error(run_id) -> None:
        execute("UPDATE runs SET status='error',ended_at=NOW() WHERE id=%s", (run_id,))

    @staticmethod
    def get(run_id, owner_id) -> dict | None:
        return query_one(
            "SELECT r.*, a.name AS api_name FROM runs r "
            "LEFT JOIN apis a ON r.api_id=a.id "
            "WHERE r.id=%s AND r.owner_id=%s",
            (run_id, owner_id)
        )

    @staticmethod
    def all_for_user(owner_id, test_type=None, limit=60) -> list:
        where  = ["r.owner_id=%s"]
        params = [owner_id]
        if test_type:
            where.append("r.test_type=%s")
            params.append(test_type)
        params.append(limit)
        return query(
            f"SELECT r.*, a.name AS api_name FROM runs r "
            f"LEFT JOIN apis a ON r.api_id=a.id "
            f"WHERE {' AND '.join(where)} ORDER BY r.started_at DESC LIMIT %s",
            params
        )


class ResultModel:

    @staticmethod
    def save(run_id, owner_id, data: dict) -> None:
        execute(
            "INSERT INTO results("
            "  run_id,owner_id,case_name,method,endpoint,test_type,"
            "  status,actual_status,expected_status,response_ms,error_msg,"
            "  assertion_detail,response_preview,resp_headers,request_data"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                run_id, owner_id,
                data.get("name", ""),
                data.get("method", ""),
                data.get("endpoint", ""),
                data.get("test_type", ""),
                data.get("status", "ERROR"),
                data.get("actual_status"),
                data.get("expected_status", 200),
                data.get("response_ms"),
                data.get("error"),
                _j(data.get("assertions", [])),
                str(data.get("response_body", ""))[:4000],
                json.dumps(data.get("resp_headers", {})) if data.get("resp_headers") else None,
                _j(data.get("request_data")),
            )
        )

    @staticmethod
    def for_run(run_id, owner_id) -> list:
        return query(
            "SELECT * FROM results WHERE run_id=%s AND owner_id=%s ORDER BY id",
            (run_id, owner_id)
        )


class LoadMetricModel:

    @staticmethod
    def save(run_id, owner_id, m: dict) -> None:
        execute(
            "INSERT INTO load_metrics("
            "  run_id,owner_id,endpoint,total_requests,passed,failed,"
            "  min_ms,max_ms,avg_ms,p95_ms,p99_ms,rps,error_rate,duration_sec,concurrency"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                run_id, owner_id,
                m.get("endpoint"), m.get("total"), m.get("passed"), m.get("failed"),
                m.get("min_ms"), m.get("max_ms"), m.get("avg_ms"),
                m.get("p95_ms"), m.get("p99_ms"), m.get("rps"),
                m.get("error_rate"), m.get("duration_sec"), m.get("concurrency"),
            )
        )

    @staticmethod
    def for_run(run_id, owner_id) -> list:
        return query(
            "SELECT * FROM load_metrics WHERE run_id=%s AND owner_id=%s",
            (run_id, owner_id)
        )


class SecurityFindingModel:

    @staticmethod
    def save(run_id, owner_id, f: dict) -> None:
        execute(
            "INSERT INTO security_findings("
            "  run_id,owner_id,endpoint,check_type,severity,passed,finding,detail"
            ") VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                run_id, owner_id,
                f.get("endpoint"), f.get("check_type"),
                f.get("severity", "info"),
                1 if f.get("passed") else 0,
                f.get("finding"), f.get("detail"),
            )
        )

    @staticmethod
    def for_run(run_id, owner_id) -> list:
        return query(
            "SELECT * FROM security_findings WHERE run_id=%s AND owner_id=%s "
            "ORDER BY FIELD(severity,'critical','high','medium','low','info')",
            (run_id, owner_id)
        )


class StatsModel:

    @staticmethod
    def for_user(owner_id) -> dict:
        return query_one(
            "SELECT "
            "  (SELECT COUNT(*) FROM my_cases  WHERE owner_id=%s) AS saved_cases,"
            "  (SELECT COUNT(*) FROM apis      WHERE owner_id=%s) AS my_apis,"
            "  (SELECT COUNT(*) FROM runs      WHERE owner_id=%s) AS total_runs,"
            "  (SELECT pass_rate FROM runs     WHERE owner_id=%s "
            "   ORDER BY started_at DESC LIMIT 1)                  AS last_rate,"
            "  (SELECT COUNT(*) FROM security_findings "
            "   WHERE owner_id=%s AND passed=0 "
            "   AND severity IN ('critical','high'))                AS open_vulns",
            (owner_id,) * 5
        ) or {}

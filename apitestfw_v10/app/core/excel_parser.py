"""
app/core/excel_parser.py — Parse uploaded Excel test case files.

Rules:
- Sheet name auto-detects test type (smoke/regression/load/stress/security)
- All columns except 'endpoint' are optional — missing = safe defaults
- APIs with no body / no params are fully supported (leave cells empty)
- JSON cells accept valid JSON strings or plain empty cells
- Tags accept comma-separated strings or JSON arrays
"""
import io
import json

import openpyxl

# Column header aliases → canonical field names
COL_ALIASES: dict[str, str] = {
    "test name": "name", "case name": "name", "case": "name", "title": "name",
    "http method": "method", "request method": "method", "verb": "method",
    "url": "endpoint", "path": "endpoint", "request url": "endpoint",
    "request body": "body", "payload": "body",
    "request headers": "headers", "header": "headers",
    "query params": "params", "query parameters": "params", "parameters": "params",
    "status": "expected_status", "status code": "expected_status",
    "expected status": "expected_status", "expected": "expected_status",
    "auth": "auth_type", "authentication": "auth_type",
    "token": "auth_token", "auth value": "auth_token",
    "max ms": "max_response_ms", "timeout ms": "max_response_ms",
    "max response ms": "max_response_ms",
    "tag": "tags", "label": "tags",
    "notes": "description", "note": "description",
    # Load extras
    "threads": "concurrency", "workers": "concurrency",
    "duration": "duration_sec", "duration s": "duration_sec",
    "duration sec": "duration_sec", "duration (sec)": "duration_sec",
    # Stress extras
    "start users": "start_users", "initial users": "start_users",
    "peak users": "peak_users", "max users": "peak_users",
    "ramp": "ramp_sec", "ramp seconds": "ramp_sec", "ramp up": "ramp_sec",
    "ramp (sec)": "ramp_sec",
    # Security extras
    "checks": "check_types", "check type": "check_types",
    "security checks": "check_types", "checks (comma-sep)": "check_types",
}

SHEET_TYPE_MAP = {
    "smoke": "smoke", "regression": "regression",
    "load": "load", "stress": "stress", "security": "security",
}


def _norm(name: str) -> str:
    s = str(name).strip().lower()
    return COL_ALIASES.get(s, s.replace(" ", "_").replace("-", "_"))


def _parse_json_cell(val, default):
    if val is None or str(val).strip() == "":
        return default
    s = str(val).strip()
    try:
        return json.loads(s)
    except Exception:
        return s  # return as raw string if not valid JSON


def _int_cell(val, default=None):
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(float(str(val).strip()))
    except Exception:
        return default


def _str_cell(val, default="") -> str:
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default


def _detect_sheet_type(name: str) -> str | None:
    s = name.strip().lower()
    for key, t in SHEET_TYPE_MAP.items():
        if s.startswith(key):
            return t
    return None


class ExcelParser:

    @staticmethod
    def parse_file(file_bytes: bytes, requested_type: str = None) -> tuple[list, str, list]:
        """
        Parse an Excel file. Returns (cases, detected_type, warnings).
        Raises ValueError if no usable sheet found.
        """
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)

        sheet         = None
        detected_type = requested_type or "regression"

        # Try to find a sheet matching requested type by name
        if requested_type:
            for ws in wb.worksheets:
                if _detect_sheet_type(ws.title) == requested_type:
                    sheet         = ws
                    detected_type = requested_type
                    break
            # Fallback: use first non-readme sheet
            if not sheet:
                for ws in wb.worksheets:
                    if ws.title.strip().lower() not in ("readme", "instructions", "help", "notes"):
                        sheet = ws
                        break
        else:
            # Auto-detect: use first sheet whose name matches a known type
            for ws in wb.worksheets:
                t = _detect_sheet_type(ws.title)
                if t:
                    sheet         = ws
                    detected_type = t
                    break
            if not sheet and wb.worksheets:
                sheet = wb.worksheets[0]

        if not sheet:
            raise ValueError("No usable worksheet found in the uploaded Excel file.")

        cases, warnings = ExcelParser._parse_sheet(sheet, detected_type)
        return cases, detected_type, warnings

    @staticmethod
    def _parse_sheet(ws, test_type: str) -> tuple[list, list]:
        rows     = list(ws.iter_rows(values_only=True))
        warnings = []
        cases    = []

        if not rows:
            return [], ["Sheet is empty."]

        # Find header row (first row containing endpoint/name/method keywords)
        header_idx = 0
        col_map: dict[int, str] = {}

        for ri, row in enumerate(rows[:6]):
            cols = {}
            for ci, cell in enumerate(row):
                if cell is not None and str(cell).strip():
                    cols[ci] = _norm(str(cell))
            if any(v in ("endpoint", "name", "method") for v in cols.values()):
                col_map    = cols
                header_idx = ri
                break

        if not col_map:
            warnings.append("Header row not detected — assuming row 1 is header.")
            if rows:
                col_map    = {ci: _norm(str(c) if c else f"col{ci}") for ci, c in enumerate(rows[0])}
                header_idx = 0

        # Parse data rows
        for ri, row in enumerate(rows[header_idx + 1:], start=header_idx + 2):
            if all(c is None or str(c).strip() == "" for c in row):
                continue  # skip empty rows

            raw: dict = {}
            for ci, field in col_map.items():
                if ci < len(row):
                    raw[field] = row[ci]

            endpoint = _str_cell(raw.get("endpoint"))
            if not endpoint:
                warnings.append(f"Row {ri}: skipped — no endpoint value.")
                continue

            # Build parsed case — all fields optional except endpoint
            parsed = {
                "name":            _str_cell(raw.get("name"), endpoint),
                "method":          _str_cell(raw.get("method"), "GET").upper(),
                "endpoint":        endpoint,
                "headers":         _parse_json_cell(raw.get("headers"), {}),
                "body":            _parse_json_cell(raw.get("body"), None),
                "params":          _parse_json_cell(raw.get("params"), {}),
                "expected_status": _int_cell(raw.get("expected_status"), 200),
                "auth_type":       _str_cell(raw.get("auth_type"), "none"),
                "auth_token":      _str_cell(raw.get("auth_token"), ""),
                "max_response_ms": _int_cell(raw.get("max_response_ms")),
                "assertions":      _parse_json_cell(raw.get("assertions"), []),
                "tags":            _parse_json_cell(raw.get("tags"), []),
                "description":     _str_cell(raw.get("description"), ""),
                "test_type":       test_type,
                "sheet_type":      test_type,
            }

            # Normalise headers/params: if they came back as plain strings try re-parse
            for fld in ("headers", "params"):
                if isinstance(parsed[fld], str):
                    try:    parsed[fld] = json.loads(parsed[fld])
                    except: parsed[fld] = {}

            # Normalise tags: comma-string → list
            if isinstance(parsed["tags"], str):
                parsed["tags"] = [t.strip() for t in parsed["tags"].split(",") if t.strip()]

            # Type-specific extras
            if test_type == "load":
                parsed["concurrency"]  = _int_cell(raw.get("concurrency"), 10)
                parsed["duration_sec"] = _int_cell(raw.get("duration_sec"), 30)
            elif test_type == "stress":
                parsed["start_users"] = _int_cell(raw.get("start_users"), 1)
                parsed["peak_users"]  = _int_cell(raw.get("peak_users"), 50)
                parsed["ramp_sec"]    = _int_cell(raw.get("ramp_sec"), 60)
            elif test_type == "security":
                raw_checks = _str_cell(raw.get("check_types"), "all")
                parsed["check_types"] = [c.strip() for c in raw_checks.split(",") if c.strip()] or ["all"]

            cases.append(parsed)

        return cases, warnings

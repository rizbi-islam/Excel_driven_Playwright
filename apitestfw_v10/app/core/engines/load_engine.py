"""
app/core/engines/load_engine.py — Concurrent load and ramp-up stress testing.
Uses ThreadPoolExecutor. No external dependencies.
"""
import itertools
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

from app.core.http_client        import HttpClient
from app.database.models.run     import LoadMetricModel


def _build_url(base_url: str, endpoint: str) -> str:
    return (endpoint if endpoint.startswith("http")
            else f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}")


def _fire(case: dict, base_url: str) -> tuple[bool, float]:
    """Send one request. Returns (passed, response_ms)."""
    method    = (case.get("method") or "GET").upper()
    url       = _build_url(base_url, case.get("endpoint", ""))
    headers   = dict(case.get("headers") or {})
    params    = dict(case.get("params")  or {})
    body      = case.get("body")
    auth_type = case.get("auth_type", "none")
    auth_tok  = case.get("auth_token", "")

    if auth_type == "bearer" and auth_tok:
        headers["Authorization"] = f"Bearer {auth_tok}"
    elif auth_type == "basic" and auth_tok:
        headers["Authorization"] = f"Basic {auth_tok}"

    body_type = "json" if body is not None else "none"
    resp      = HttpClient.send(method=method, url=url, headers=headers,
                                params=params, body_type=body_type, body=body, timeout=30)
    expected  = int(case.get("expected_status") or 200)
    return resp["status"] == expected, resp["response_ms"]


def run_load(cases: list, base_url: str, run_id: int, owner_id: int,
             concurrency: int = 10, duration_sec: int = 30) -> dict:
    """
    Drive N concurrent workers looping all cases for `duration_sec` seconds.
    Saves aggregate metrics to DB.
    """
    if not cases:
        return dict(total=0, passed=0, failed=0, duration=0, pass_rate=0)

    concurrency  = max(1, min(concurrency, 200))
    duration_sec = max(5, min(duration_sec, 600))

    lock        = threading.Lock()
    stop        = threading.Event()
    times: list = []
    counts      = {"total": 0, "passed": 0, "failed": 0}
    cycle_lock  = threading.Lock()
    cycle       = itertools.cycle(cases)

    def worker():
        while not stop.is_set():
            with cycle_lock:
                case = next(cycle)
            ok, ms = _fire(case, base_url)
            with lock:
                times.append(ms)
                counts["total"]  += 1
                counts["passed"] += 1 if ok else 0
                counts["failed"] += 0 if ok else 1

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as exe:
        futures = [exe.submit(worker) for _ in range(concurrency)]
        time.sleep(duration_sec)
        stop.set()
        wait(futures, timeout=15)
    wall = round(time.perf_counter() - wall_start, 2)

    _save_metrics(times, counts, wall, concurrency, cases[0].get("endpoint",""), run_id, owner_id)

    t = counts["total"]; p = counts["passed"]
    return dict(total=t, passed=p, failed=counts["failed"], duration=wall,
                pass_rate=round(p / t * 100, 1) if t else 0)


def run_stress(cases: list, base_url: str, run_id: int, owner_id: int,
               start_users: int = 1, peak_users: int = 50, ramp_sec: int = 60) -> dict:
    """
    Ramp from start_users → peak_users over ramp_sec, hold 30s at peak, then stop.
    """
    if not cases:
        return dict(total=0, passed=0, failed=0, duration=0, pass_rate=0)

    start_users = max(1, min(start_users, 50))
    peak_users  = max(start_users, min(peak_users, 200))
    ramp_sec    = max(10, min(ramp_sec, 600))
    hold_sec    = 30

    lock        = threading.Lock()
    stop        = threading.Event()
    times: list = []
    counts      = {"total": 0, "passed": 0, "failed": 0}
    cycle_lock  = threading.Lock()
    cycle       = itertools.cycle(cases)

    def worker():
        while not stop.is_set():
            with cycle_lock:
                case = next(cycle)
            ok, ms = _fire(case, base_url)
            with lock:
                times.append(ms)
                counts["total"]  += 1
                counts["passed"] += 1 if ok else 0
                counts["failed"] += 0 if ok else 1

    steps      = max(peak_users - start_users, 1)
    step_delay = ramp_sec / steps
    wall_start = time.perf_counter()
    all_futures = []

    with ThreadPoolExecutor(max_workers=peak_users + 10) as exe:
        for _ in range(start_users):
            all_futures.append(exe.submit(worker))
        for _ in range(steps):
            time.sleep(step_delay)
            if not stop.is_set():
                all_futures.append(exe.submit(worker))
        time.sleep(hold_sec)
        stop.set()
        wait(all_futures, timeout=20)

    wall = round(time.perf_counter() - wall_start, 2)
    _save_metrics(times, counts, wall, peak_users, cases[0].get("endpoint",""), run_id, owner_id)

    t = counts["total"]; p = counts["passed"]
    return dict(total=t, passed=p, failed=counts["failed"], duration=wall,
                pass_rate=round(p / t * 100, 1) if t else 0)


def _save_metrics(times: list, counts: dict, wall: float, concurrency: int,
                  endpoint: str, run_id: int, owner_id: int):
    if not times:
        return
    st = sorted(times)
    n  = len(st)
    LoadMetricModel.save(run_id, owner_id, dict(
        endpoint     = endpoint,
        total        = counts["total"],
        passed       = counts["passed"],
        failed       = counts["failed"],
        min_ms       = round(st[0], 2),
        max_ms       = round(st[-1], 2),
        avg_ms       = round(sum(st) / n, 2),
        p95_ms       = round(st[max(0, int(n * 0.95) - 1)], 2),
        p99_ms       = round(st[max(0, int(n * 0.99) - 1)], 2),
        rps          = round(counts["total"] / wall, 2) if wall > 0 else 0,
        error_rate   = round(counts["failed"] / counts["total"] * 100, 2) if counts["total"] else 0,
        duration_sec = wall,
        concurrency  = concurrency,
    ))

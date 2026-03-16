"""
app/core/report_generator.py — Generate a self-contained HTML report.
No external dependencies. Single file, opens in any browser, no server needed.
"""
import json
from datetime import datetime


def generate_html_report(collection_name: str, report: dict) -> str:
    """
    Returns a self-contained HTML string.
    report = { summary: {...}, results: [...] }
    """
    summary = report.get("summary", {})
    results = report.get("results", [])
    now     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pass_rate   = summary.get("pass_rate", 0)
    bar_color   = "#22c55e" if pass_rate >= 80 else "#f59e0b" if pass_rate >= 50 else "#ef4444"
    total_reqs  = summary.get("total_requests", 0)
    req_passed  = summary.get("request_passed", 0)
    req_failed  = summary.get("request_failed", 0)
    total_tests = summary.get("total_tests", 0)
    t_passed    = summary.get("tests_passed", 0)
    t_failed    = summary.get("tests_failed", 0)
    total_ms    = summary.get("total_time_ms", 0)

    def _esc(s):
        return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

    def _status_color(code):
        if not code: return "#64748b"
        if code < 300: return "#22c55e"
        if code < 400: return "#f59e0b"
        return "#ef4444"

    def _method_color(m):
        colors = {"GET":"#4f8eff","POST":"#22c55e","PUT":"#f59e0b","PATCH":"#f97316","DELETE":"#ef4444"}
        return colors.get(str(m).upper(), "#a855f7")

    def _fmt_ms(ms):
        if not ms: return "0ms"
        ms = float(ms)
        return f"{ms:.0f}ms" if ms < 1000 else f"{ms/1000:.2f}s"

    # Build result rows
    rows_html = ""
    for i, r in enumerate(results):
        is_skip   = r.get("skipped", False)
        req_pass  = r.get("request_passed", False)
        tests     = r.get("tests", [])
        console   = r.get("console", [])
        error     = r.get("error", "")
        body      = (r.get("body") or "")[:3000]

        if is_skip:
            icon = "⏭"; row_bg = "#1e293b"; badge_bg = "#334155"; badge_fg = "#94a3b8"
        elif req_pass:
            icon = "✅"; row_bg = "#0f2a1f"; badge_bg = "#166534"; badge_fg = "#86efac"
        else:
            icon = "❌"; row_bg = "#2a0f0f"; badge_bg = "#7f1d1d"; badge_fg = "#fca5a5"

        test_rows = ""
        for t in tests:
            tc = "#86efac" if t["passed"] else "#fca5a5"
            ti = "✓" if t["passed"] else "✗"
            err_str = f' <span style="color:#94a3b8;font-size:.75rem">({_esc(t.get("error",""))})</span>' if t.get("error") else ""
            test_rows += f'<div style="padding:.25rem .5rem .25rem 2rem;font-size:.78rem;color:{tc}">{ti} {_esc(t["name"])}{err_str}</div>'

        console_rows = ""
        for log in console:
            lc = {"warn":"#fbbf24","error":"#f87171"}.get(log.get("level"), "#94a3b8")
            console_rows += f'<div style="padding:.2rem .5rem .2rem 2rem;font-size:.73rem;color:{lc}">[{log.get("level","log")}] {_esc(log.get("msg",""))}</div>'

        body_section = ""
        if body:
            body_esc = _esc(body)
            body_section = f'''
            <details style="margin:.3rem 0 .3rem 1.2rem">
              <summary style="cursor:pointer;font-size:.75rem;color:#94a3b8;user-select:none">Response Body</summary>
              <pre style="background:#0d1117;border-radius:6px;padding:.75rem;font-size:.72rem;
                          font-family:'JetBrains Mono',monospace;color:#e2e8f0;
                          overflow-x:auto;margin:.4rem 0;max-height:200px;overflow-y:auto">{body_esc}</pre>
            </details>'''

        error_section = f'<div style="padding:.3rem .5rem .3rem 1.2rem;color:#fca5a5;font-size:.78rem">⚠ {_esc(error)}</div>' if error else ""

        expandable = test_rows or console_rows or body_section or error_section
        detail_id  = f"detail-{i}"

        rows_html += f'''
        <div style="border:1px solid #2e3850;border-radius:8px;margin-bottom:.6rem;overflow:hidden">
          <div style="padding:.65rem 1rem;background:{row_bg};display:flex;align-items:center;gap:.75rem;
                      cursor:{'pointer' if expandable else 'default'}"
               {'onclick="toggleDetail(\''+detail_id+'\')"' if expandable else ''}>
            <span style="font-size:1.1rem;flex-shrink:0">{icon}</span>
            <span style="background:{_method_color(r.get('method','GET'))};color:#fff;
                         font-family:monospace;font-size:.68rem;font-weight:700;
                         padding:.15rem .45rem;border-radius:4px;flex-shrink:0">{_esc(r.get('method',''))}</span>
            <span style="font-weight:600;font-size:.85rem;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{_esc(r.get('name',''))}</span>
            <span style="font-family:monospace;font-size:.82rem;color:{_status_color(r.get('status'))};font-weight:700;flex-shrink:0">{r.get('status') or '—'}</span>
            <span style="color:#64748b;font-size:.78rem;flex-shrink:0">{_fmt_ms(r.get('response_ms'))}</span>
            {f'<span style="background:{badge_bg};color:{badge_fg};font-size:.68rem;padding:.15rem .5rem;border-radius:20px">{len([t for t in tests if t["passed"]])}/{len(tests)} tests</span>' if tests else ''}
            {'<span style="color:#64748b;font-size:.8rem">▾</span>' if expandable else ''}
          </div>
          {f'<div id="{detail_id}" style="display:none;border-top:1px solid #2e3850">{error_section}{test_rows}{console_rows}{body_section}</div>' if expandable else ''}
        </div>'''

    # Assemble full HTML
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Collection Report — {_esc(collection_name)}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Inter', system-ui, sans-serif; background: #0d1117;
          color: #e2e8f0; font-size: 14px; line-height: 1.5; padding: 2rem; }}
  .container {{ max-width: 960px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: .25rem; }}
  .meta {{ color: #64748b; font-size: .82rem; margin-bottom: 1.5rem; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px,1fr));
              gap: .75rem; margin-bottom: 1.5rem; }}
  .stat {{ background: #161b27; border: 1px solid #2e3850; border-radius: 10px;
           padding: 1rem 1.2rem; }}
  .stat-label {{ font-size: .68rem; color: #64748b; text-transform: uppercase;
                  letter-spacing: .07em; margin-bottom: .2rem; }}
  .stat-val {{ font-size: 1.8rem; font-weight: 700; }}
  .progress-bar {{ height: 8px; background: #2e3850; border-radius: 4px;
                   overflow: hidden; margin-bottom: 1.5rem; }}
  .progress-fill {{ height: 100%; background: {bar_color}; border-radius: 4px;
                    width: {min(pass_rate, 100)}%; transition: width .5s; }}
  .section-title {{ font-size: .78rem; font-weight: 700; color: #94a3b8;
                    text-transform: uppercase; letter-spacing: .08em; margin-bottom: .75rem; }}
  details summary::-webkit-details-marker {{ display: none; }}
  @media print {{
    body {{ background: white; color: black; }}
    .stat {{ background: #f8f9fa; border-color: #dee2e6; }}
  }}
</style>
</head>
<body>
<div class="container">

  <h1>📊 {_esc(collection_name)}</h1>
  <div class="meta">Generated: {now} &nbsp;·&nbsp; API Test Framework v10</div>

  <div class="progress-bar"><div class="progress-fill"></div></div>

  <div class="summary">
    <div class="stat">
      <div class="stat-label">Pass Rate</div>
      <div class="stat-val" style="color:{bar_color}">{pass_rate}%</div>
    </div>
    <div class="stat">
      <div class="stat-label">Requests</div>
      <div class="stat-val" style="color:#4f8eff">{total_reqs}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Passed</div>
      <div class="stat-val" style="color:#22c55e">{req_passed}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Failed</div>
      <div class="stat-val" style="color:{'#ef4444' if req_failed else '#22c55e'}">{req_failed}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Tests</div>
      <div class="stat-val" style="color:#a855f7">{total_tests}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Tests Passed</div>
      <div class="stat-val" style="color:#22c55e">{t_passed}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Tests Failed</div>
      <div class="stat-val" style="color:{'#ef4444' if t_failed else '#22c55e'}">{t_failed}</div>
    </div>
    <div class="stat">
      <div class="stat-label">Total Time</div>
      <div class="stat-val" style="color:#94a3b8;font-size:1.2rem">{_fmt_ms(total_ms)}</div>
    </div>
  </div>

  <div class="section-title">Request Results</div>
  <div id="results">
    {rows_html if rows_html else '<div style="padding:2rem;text-align:center;color:#64748b">No results</div>'}
  </div>

</div>
<script>
function toggleDetail(id) {{
  var el = document.getElementById(id);
  if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}}
</script>
</body>
</html>'''

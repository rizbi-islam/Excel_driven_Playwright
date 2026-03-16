/**
 * runs.js — Excel upload + library run pipeline.
 * Used by all 5 run pages (smoke/regression/load/stress/security).
 */
const RunPage = (() => {
  let currentRunId = null;

  /* ── Upload & run from Excel ────────────────────────────────── */
  async function runFromExcel(testType) {
    const fileInput = document.getElementById('excel-file');
    const baseUrl   = document.getElementById('base-url')?.value?.trim();
    const label     = document.getElementById('run-label')?.value?.trim() || `${testType} run`;
    const apiId     = document.getElementById('api-sel')?.value || '';

    if (!fileInput?.files[0]) { Toast.error('Please select an Excel file'); return; }
    if (!baseUrl)             { Toast.error('Base URL is required'); return; }

    const form = new FormData();
    form.append('file',      fileInput.files[0]);
    form.append('base_url',  baseUrl);
    form.append('test_type', testType);
    form.append('label',     label);
    if (apiId) form.append('api_id', apiId);

    // Extra params for load/stress
    _appendExtra(form, testType);

    _showStatus('Uploading and parsing Excel…');

    const resp = await fetch('/api/run/excel', { method: 'POST', body: form });
    const data = await resp.json().catch(() => ({ ok: false, error: 'Server error' }));

    if (!data.ok) { Toast.error(data.error || 'Failed to start run'); _hideStatus(); return; }

    if (data.warnings?.length) {
      data.warnings.forEach(w => Toast.warn(w));
    }

    currentRunId = data.run_id;
    _showStatus(`Started: ${data.total_cases} cases — polling…`, data.run_id);
    Toast.info(`Run #${data.run_id} started with ${data.total_cases} cases`);

    pollRunStatus(data.run_id,
      run => _onProgress(run),
      (run, err) => _onDone(run, err)
    );
  }

  /* ── Run from library ───────────────────────────────────────── */
  async function runFromLibrary(testType) {
    const baseUrl = document.getElementById('base-url')?.value?.trim();
    const apiId   = document.getElementById('api-sel')?.value || null;
    const label   = document.getElementById('run-label')?.value?.trim() || `${testType} run`;

    if (!baseUrl) { Toast.error('Base URL is required'); return; }

    const body = {
      base_url:   baseUrl,
      test_type:  testType,
      sheet_type: testType,
      label,
      api_id:     apiId || undefined,
      ..._getExtra(testType),
    };

    _showStatus('Loading library cases…');
    const data = await apiFetch('/api/run/library', { body });

    if (!data.ok) { Toast.error(data.error || 'Failed to start run'); _hideStatus(); return; }

    currentRunId = data.run_id;
    _showStatus(`Started: ${data.total_cases} cases — polling…`, data.run_id);

    pollRunStatus(data.run_id,
      run => _onProgress(run),
      (run, err) => _onDone(run, err)
    );
  }

  /* ── Save run to library ─────────────────────────────────────── */
  async function saveToLibrary(runId, onlyPassed = false) {
    const apiId = document.getElementById('api-sel')?.value || null;
    const data  = await apiFetch(`/api/run/${runId}/save-to-library`, {
      body: { api_id: apiId, only_passed: onlyPassed },
    });
    if (data.ok) Toast.success(`Saved ${data.saved} test cases to library ✓`);
    else         Toast.error(data.error || 'Save failed');
  }

  /* ── Progress / done callbacks ──────────────────────────────── */
  function _onProgress(run) {
    const el = document.getElementById('run-progress-text');
    if (el) el.textContent = `Running… ${run.passed + run.failed}/${run.total} done`;
  }

  function _onDone(run, err) {
    if (err || !run) {
      Toast.error(`Run failed: ${err || 'Unknown error'}`);
      _hideStatus();
      return;
    }
    if (run.status === 'error') {
      Toast.error('Run encountered errors. Check results.');
    } else {
      const rate = run.pass_rate;
      const emoji = rate >= 90 ? '✅' : rate >= 60 ? '⚠️' : '❌';
      Toast.success(`${emoji} Run complete: ${run.passed}/${run.total} passed (${rate}%)`);
    }
    _renderSummary(run);
    _loadResults(run.id);
  }

  function _renderSummary(run) {
    const panel = document.getElementById('run-summary');
    if (!panel) return;
    panel.style.display = '';
    panel.innerHTML = `
      <div class="run-counters">
        <div class="run-counter"><div class="run-counter-val c-blue">${run.total}</div><div class="run-counter-label">Total</div></div>
        <div class="run-counter"><div class="run-counter-val c-green">${run.passed}</div><div class="run-counter-label">Passed</div></div>
        <div class="run-counter"><div class="run-counter-val c-red">${run.failed}</div><div class="run-counter-label">Failed</div></div>
        <div class="run-counter"><div class="run-counter-val ${passRateColor(run.pass_rate)}">${run.pass_rate}%</div><div class="run-counter-label">Pass Rate</div></div>
        <div class="run-counter"><div class="run-counter-val text-muted">${run.duration_sec}s</div><div class="run-counter-label">Duration</div></div>
      </div>
      <div class="flex gap-1 mt" style="margin-top:.75rem">
        <a href="/result/${run.id}" class="btn btn-secondary btn-sm">📊 View Full Results</a>
        <button class="btn btn-success btn-sm" onclick="RunPage.saveToLibrary(${run.id})">💾 Save to Library</button>
        <button class="btn btn-ghost btn-sm" onclick="RunPage.saveToLibrary(${run.id}, true)">💾 Save Passed Only</button>
      </div>`;
  }

  async function _loadResults(runId) {
    const tbody = document.getElementById('results-tbody');
    if (!tbody) return;

    const data = await apiFetch(`/api/run/${runId}/results`);
    if (!data.ok) return;

    // For load/stress — show metrics
    if (data.metrics?.length) {
      _renderMetrics(data.metrics);
      return;
    }
    // For security — show findings
    if (data.findings?.length) {
      _renderFindings(data.findings);
      return;
    }
    // Smoke / regression
    _renderResultRows(tbody, data.results);
  }

  function _renderResultRows(tbody, results) {
    tbody.innerHTML = '';
    for (const r of results || []) {
      const pass = r.status === 'PASS';
      const tr   = document.createElement('tr');
      tr.className = pass ? 'result-pass' : 'result-fail';
      tr.innerHTML = `
        <td>${methodBadge(r.method)}</td>
        <td class="text-mono text-sm truncate" style="max-width:280px" title="${r.endpoint}">${r.endpoint}</td>
        <td>${pass ? '<span class="badge bg-green">PASS</span>' : '<span class="badge bg-red">FAIL</span>'}</td>
        <td class="${statusClass(r.actual_status)}">${r.actual_status || '—'}</td>
        <td class="text-muted text-sm">${fmtMs(r.response_ms)}</td>
        <td class="text-muted text-sm truncate" style="max-width:200px">${r.case_name || '—'}</td>`;
      tbody.appendChild(tr);
    }
    if (!results?.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted" style="padding:2rem">No results</td></tr>';
    }
  }

  function _renderMetrics(metrics) {
    const el = document.getElementById('metrics-panel');
    if (!el) return;
    el.style.display = '';
    let html = `<div class="tbl-wrap"><table>
      <thead><tr>
        <th>Endpoint</th><th>Requests</th><th>Pass</th><th>Fail</th>
        <th>Avg</th><th>P95</th><th>P99</th><th>RPS</th><th>Errors</th>
      </tr></thead><tbody>`;
    for (const m of metrics) {
      html += `<tr>
        <td class="text-mono text-sm">${m.endpoint}</td>
        <td>${m.total_requests}</td>
        <td class="c-green">${m.passed}</td>
        <td class="c-red">${m.failed}</td>
        <td>${fmtMs(m.avg_ms)}</td>
        <td>${fmtMs(m.p95_ms)}</td>
        <td>${fmtMs(m.p99_ms)}</td>
        <td>${m.rps}</td>
        <td class="${m.error_rate > 5 ? 'c-red' : 'c-green'}">${m.error_rate}%</td>
      </tr>`;
    }
    html += '</tbody></table></div>';
    el.innerHTML = html;
  }

  function _renderFindings(findings) {
    const el = document.getElementById('findings-panel');
    if (!el) return;
    el.style.display = '';
    const sev = { critical:'bg-red',high:'bg-red',medium:'bg-orange',low:'bg-yellow',info:'bg-blue' };
    let html = `<div class="tbl-wrap"><table>
      <thead><tr><th>Endpoint</th><th>Check</th><th>Severity</th><th>Result</th><th>Finding</th></tr></thead><tbody>`;
    for (const f of findings) {
      html += `<tr>
        <td class="text-mono text-sm">${f.endpoint}</td>
        <td>${f.check_type}</td>
        <td><span class="badge ${sev[f.severity]||'bg-gray'}">${f.severity}</span></td>
        <td>${f.passed ? '<span class="badge bg-green">PASS</span>' : '<span class="badge bg-red">FAIL</span>'}</td>
        <td class="text-sm">${f.finding}</td>
      </tr>`;
    }
    html += '</tbody></table></div>';
    el.innerHTML = html;
  }

  /* ── Status panel helpers ────────────────────────────────────── */
  function _showStatus(msg, runId = null) {
    const panel = document.getElementById('run-status-panel');
    if (!panel) return;
    panel.classList.add('visible');
    const txt = document.getElementById('run-progress-text');
    if (txt) txt.textContent = msg;
    const bar = document.getElementById('run-prog-bar');
    if (bar) bar.classList.add('prog-indeterminate');
    if (runId) {
      const link = document.getElementById('run-detail-link');
      if (link) { link.href = `/result/${runId}`; link.style.display = ''; }
    }
  }

  function _hideStatus() {
    const panel = document.getElementById('run-status-panel');
    if (panel) panel.classList.remove('visible');
  }

  function _appendExtra(form, testType) {
    if (testType === 'load') {
      const c = document.getElementById('concurrency')?.value;
      const d = document.getElementById('duration-sec')?.value;
      if (c) form.append('concurrency', c);
      if (d) form.append('duration_sec', d);
    } else if (testType === 'stress') {
      ['start-users','peak-users','ramp-sec'].forEach(id => {
        const v = document.getElementById(id)?.value;
        if (v) form.append(id.replace('-','_'), v);
      });
    }
  }

  function _getExtra(testType) {
    const out = {};
    if (testType === 'load') {
      out.concurrency  = parseInt(document.getElementById('concurrency')?.value  || 10);
      out.duration_sec = parseInt(document.getElementById('duration-sec')?.value || 30);
    } else if (testType === 'stress') {
      out.start_users = parseInt(document.getElementById('start-users')?.value || 1);
      out.peak_users  = parseInt(document.getElementById('peak-users')?.value  || 50);
      out.ramp_sec    = parseInt(document.getElementById('ramp-sec')?.value     || 60);
    }
    return out;
  }

  return { runFromExcel, runFromLibrary, saveToLibrary };
})();

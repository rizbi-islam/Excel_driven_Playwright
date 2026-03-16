/**
 * collections.js — Full Collection Manager (Postman-parity).
 * Variables, pre/post scripts, collection runner with report.
 */
const CM = (() => {
  let _currentColId  = null;
  let _currentReqId  = null;
  let _currentCol    = null;
  let _requests      = [];
  let _runnerReport  = null;

  function init() {
    // If URL has ?col=N, open that collection
    const p = new URLSearchParams(location.search);
    if (p.get('col')) openCollection(parseInt(p.get('col')));
  }

  /* ── Sidebar helpers ──────────────────────────────────────── */
  function _setActiveCol(id) {
    document.querySelectorAll('.col-item').forEach(el => {
      el.style.background = el.id === `col-item-${id}` ? 'var(--accent-dim)' : '';
      el.style.borderLeft = el.id === `col-item-${id}` ? '2px solid var(--accent)' : '';
    });
  }

  /* ── Open / load collection ───────────────────────────────── */
  async function openCollection(id) {
    _currentColId = id;
    _currentReqId = null;
    _setActiveCol(id);

    const data = await apiFetch(`/api/collections/${id}`);
    if (!data.ok) { Toast.error('Failed to load collection'); return; }

    _currentCol = data.collection;
    _requests   = data.requests;

    document.getElementById('detail-empty').style.display  = 'none';
    document.getElementById('detail-panel').style.display  = 'flex';
    document.getElementById('col-name-display').textContent = _currentCol.name;

    _renderRequestList();

    // Hide editor
    document.getElementById('req-editor').style.display = 'none';
  }

  function _renderRequestList() {
    const list = document.getElementById('req-list');
    if (!list) return;
    if (!_requests.length) {
      list.innerHTML = '<div style="padding:1.5rem;text-align:center;color:var(--text3);font-size:.78rem">No requests yet.<br>Click <strong>+ Add</strong> to create one.</div>';
      return;
    }
    const mCls = {GET:'bg-blue',POST:'bg-green',PUT:'bg-yellow',PATCH:'bg-orange',DELETE:'bg-red',HEAD:'bg-gray',OPTIONS:'bg-gray'};
    list.innerHTML = _requests.map(r => `
      <div class="req-list-item ${r.id === _currentReqId ? 'active' : ''}" id="rli-${r.id}"
           onclick="CM.openRequest(${r.id})">
        <span class="badge ${mCls[r.method]||'bg-gray'} text-mono" style="font-size:.6rem;padding:.1rem .35rem">${r.method}</span>
        <span class="truncate text-sm" style="flex:1">${_esc(r.name)}</span>
      </div>`).join('');
  }

  /* ── Open request in editor ────────────────────────────────── */
  async function openRequest(rid) {
    _currentReqId = rid;

    // Mark active in list
    document.querySelectorAll('.req-list-item').forEach(el => el.classList.remove('active'));
    document.getElementById(`rli-${rid}`)?.classList.add('active');

    const data = await apiFetch(`/api/collections/requests/${rid}`);
    if (!data.ok) { Toast.error('Load failed'); return; }

    const r = data.request;
    document.getElementById('req-editor').style.display   = 'flex';
    document.getElementById('req-resp-card').style.display = 'none';

    // Fill fields
    document.getElementById('req-name-inp').value  = r.name   || '';
    document.getElementById('req-url').value        = r.url    || '';
    document.getElementById('req-method').value     = r.method || 'GET';
    document.getElementById('req-pre-script').value  = r.pre_request_script || '';
    document.getElementById('req-tests-script').value = r.tests_script || '';
    document.getElementById('req-description').value  = r.description || '';

    // Params / headers KV
    if (window.kvReqParams)  window.kvReqParams.load(r.params  || {});
    if (window.kvReqHeaders) window.kvReqHeaders.load(r.headers || {});

    // Body
    const btype = r.body_type || 'none';
    const bBtn  = document.querySelector(`.body-type-btn[data-type="${btype}"]`);
    if (bBtn) setReqBodyType(btype, bBtn);

    if (btype === 'form' || btype === 'urlencoded') {
      if (window.kvReqBodyForm && typeof r.body === 'object' && r.body)
        window.kvReqBodyForm.load(r.body);
    } else if (btype === 'multipart') {
      if (window.kvReqBodyMulti && typeof r.body === 'object' && r.body)
        window.kvReqBodyMulti.load(r.body);
    } else if (r.body && btype !== 'none') {
      const area = document.getElementById('req-body-area');
      if (area) area.value = typeof r.body === 'string' ? r.body : JSON.stringify(r.body, null, 2);
    }

    // Auth
    const authSel = document.getElementById('req-auth-type');
    if (authSel) { authSel.value = r.auth_type || 'inherit'; onReqAuthChange(); }
    setTimeout(() => {
      const av = document.getElementById('req-auth-value');
      if (av) av.value = r.auth_token || '';
    }, 60);

    // Show first tab
    const firstTab = document.querySelector('.req-editor-tab.active');
    if (!firstTab) showReqTab('params', document.querySelector('.req-editor-tab'));
  }

  /* ── New request ────────────────────────────────────────────── */
  function newRequest() {
    _currentReqId = null;
    document.getElementById('req-editor').style.display    = 'flex';
    document.getElementById('req-resp-card').style.display = 'none';
    document.getElementById('req-name-inp').value           = '';
    document.getElementById('req-url').value                = '';
    document.getElementById('req-method').value             = 'GET';
    document.getElementById('req-pre-script').value         = '';
    document.getElementById('req-tests-script').value       = '';
    document.getElementById('req-description').value        = '';
    window.kvReqParams?.clear();
    window.kvReqHeaders?.clear();
    window.kvReqBodyForm?.clear();
    window.kvReqBodyMulti?.clear();
    const area = document.getElementById('req-body-area');
    if (area) area.value = '';
    const noneBtn = document.querySelector('.body-type-btn[data-type="none"]');
    if (noneBtn) setReqBodyType('none', noneBtn);
    document.querySelectorAll('.req-list-item').forEach(el => el.classList.remove('active'));
    document.getElementById('req-name-inp')?.focus();
  }

  /* ── Save request ────────────────────────────────────────────── */
  async function saveRequest() {
    const name   = document.getElementById('req-name-inp').value.trim();
    const url    = document.getElementById('req-url').value.trim();
    const method = document.getElementById('req-method').value;
    if (!url) { Toast.error('URL is required'); return; }

    const body_type = document.querySelector('.body-type-btn.active')?.dataset.type || 'none';
    let body = null;
    if (body_type === 'form' || body_type === 'urlencoded') {
      body = window.kvReqBodyForm?.getDict() || null;
    } else if (body_type === 'multipart') {
      body = window.kvReqBodyMulti?.getDict() || null;
    } else if (body_type !== 'none') {
      const raw = document.getElementById('req-body-area')?.value || '';
      if (raw.trim()) {
        try   { body = JSON.parse(raw); }
        catch { body = raw; }
      }
    }

    const authType  = document.getElementById('req-auth-type')?.value || 'inherit';
    const authToken = document.getElementById('req-auth-value')?.value || '';
    const authKey   = document.getElementById('req-auth-key-name')?.value || 'X-API-Key';

    const payload = {
      name:               name || url,
      method,
      url,
      headers:            window.kvReqHeaders?.getDict() || {},
      params:             window.kvReqParams?.getDict()  || {},
      body,
      body_type,
      auth_type:          authType,
      auth_token:         authToken,
      auth_key_name:      authKey,
      pre_request_script: document.getElementById('req-pre-script')?.value || '',
      tests_script:       document.getElementById('req-tests-script')?.value || '',
      description:        document.getElementById('req-description')?.value || '',
    };

    let data;
    if (_currentReqId) {
      data = await apiFetch(`/api/collections/requests/${_currentReqId}/update`, { body: payload });
    } else {
      data = await apiFetch(`/api/collections/${_currentColId}/requests`, { body: payload });
      if (data.ok) _currentReqId = data.id;
    }

    if (data.ok) {
      Toast.success('Saved ✓');
      await openCollection(_currentColId);
      if (_currentReqId) {
        setTimeout(() => openRequest(_currentReqId), 100);
      }
    } else {
      Toast.error(data.error || 'Save failed');
    }
  }

  /* ── Send request from editor ────────────────────────────────── */
  async function sendRequest() {
    const url    = document.getElementById('req-url').value.trim();
    const method = document.getElementById('req-method').value;
    if (!url) { Toast.error('URL is required'); return; }

    const body_type = document.querySelector('.body-type-btn.active')?.dataset.type || 'none';
    let body = null, headers = window.kvReqHeaders?.getDict() || {};
    if (body_type === 'form' || body_type === 'urlencoded') {
      body = window.kvReqBodyForm?.getDict() || null;
    } else if (body_type === 'multipart') {
      body = window.kvReqBodyMulti?.getDict() || null;
    } else if (body_type !== 'none') {
      const raw = document.getElementById('req-body-area')?.value || '';
      if (raw.trim()) {
        try   { body = JSON.parse(raw); }
        catch { body = raw; }
      }
    }

    const authType = document.getElementById('req-auth-type')?.value || 'none';
    const authTok  = document.getElementById('req-auth-value')?.value || '';
    const authKey  = document.getElementById('req-auth-key-name')?.value || 'X-API-Key';
    const params   = window.kvReqParams?.getDict() || {};

    const resp = await apiFetch('/api/send-request', { body: {
      method, url, headers, params, body, body_type,
      auth_type: authType === 'inherit' ? (_currentCol?.auth_type||'none') : authType,
      auth_value: authType === 'inherit' ? (_currentCol?.auth_token||'') : authTok,
      auth_key_name: authKey,
    }});

    const card  = document.getElementById('req-resp-card');
    const bEl   = document.getElementById('req-resp-body');
    const sEl   = document.getElementById('req-resp-status');
    const msEl  = document.getElementById('req-resp-ms');
    if (card) card.style.display = '';
    if (sEl)  { sEl.textContent = `${resp.status} ${resp.status_text||''}`; sEl.className = `fw6 ${statusClass(resp.status)}`; }
    if (msEl) msEl.textContent = fmtMs(resp.response_ms);
    if (bEl)  bEl.textContent = resp.body || '(empty)';
    Toast[resp.ok ? 'success' : 'warn'](`${resp.status} ${resp.status_text||''} — ${fmtMs(resp.response_ms)}`);
  }

  function showRespTab(name, el) {
    document.getElementById('req-resp-body').style.display    = name === 'body'    ? '' : 'none';
    document.getElementById('req-resp-headers').style.display = name === 'headers' ? '' : 'none';
  }

  /* ── Delete request ─────────────────────────────────────────── */
  async function deleteRequest() {
    if (!_currentReqId) return;
    if (!confirm('Delete this request?')) return;
    const data = await apiFetch(`/api/collections/requests/${_currentReqId}/delete`, { body: {} });
    if (data.ok) {
      Toast.success('Deleted');
      _currentReqId = null;
      document.getElementById('req-editor').style.display = 'none';
      await openCollection(_currentColId);
    } else Toast.error(data.error || 'Delete failed');
  }

  /* ── Body type ─────────────────────────────────────────────── */
  function setReqBodyType(type, el) {
    document.querySelectorAll('.body-type-btn').forEach(b => b.classList.remove('active'));
    el?.classList.add('active');
    ['req-body-none','req-body-area','req-body-form-wrap','req-body-multi-wrap'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    if (type === 'none') {
      document.getElementById('req-body-none').style.display = '';
    } else if (type === 'form' || type === 'urlencoded') {
      document.getElementById('req-body-form-wrap').style.display = '';
      if (window.kvReqBodyForm && !document.querySelector('#req-body-form-tbody tr')) window.kvReqBodyForm.addRow();
    } else if (type === 'multipart') {
      document.getElementById('req-body-multi-wrap').style.display = '';
      if (window.kvReqBodyMulti && !document.querySelector('#req-body-multi-tbody tr')) window.kvReqBodyMulti.addRow();
    } else {
      document.getElementById('req-body-area').style.display = '';
      const ph = { json:'{\n  "key": "value"\n}', xml:'<root/>', graphql:'{ users { id } }', raw:'' };
      document.getElementById('req-body-area').placeholder = ph[type] || '';
    }
  }

  /* ── Request editor tabs ────────────────────────────────────── */
  function showReqTab(name, el) {
    document.querySelectorAll('.req-editor-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.req-editor-panel').forEach(p => p.style.display = 'none');
    el?.classList.add('active');
    const panel = document.getElementById(`rep-${name}`);
    if (panel) panel.style.display = '';
  }

  /* ── Auth fields ────────────────────────────────────────────── */
  function onReqAuthChange() {
    const type = document.getElementById('req-auth-type')?.value || 'inherit';
    const box  = document.getElementById('req-auth-fields');
    if (!box) return;
    const tpls = {
      bearer: `<div class="grid2" style="gap:.5rem"><div class="form-group"><label class="label">Token</label><input id="req-auth-value" class="input input-mono" placeholder="eyJ…"/></div></div>`,
      basic:  `<div class="form-group"><label class="label">Base64 Credentials</label><input id="req-auth-value" class="input input-mono" placeholder="dXNlcjpwYXNz"/></div>`,
      apikey: `<div class="grid2" style="gap:.5rem">
        <div class="form-group"><label class="label">Header Name</label><input id="req-auth-key-name" class="input" value="X-API-Key"/></div>
        <div class="form-group"><label class="label">Value</label><input id="req-auth-value" class="input input-mono" placeholder="key-value"/></div></div>`,
      inherit:`<p class="text-muted text-sm">Using collection-level auth: <strong>${_currentCol?.auth_type||'none'}</strong></p>`,
      none:   `<p class="text-muted text-sm">No authentication will be sent with this request.</p>`,
    };
    box.innerHTML = tpls[type] || '';
  }

  /* ── Collection settings ────────────────────────────────────── */
  function showSettings() {
    if (!_currentCol) return;
    const p = document.getElementById('settings-panel');
    if (p.style.display === 'none' || !p.style.display) {
      p.style.display = '';
      _loadSettingsFromCol();
      showSettingsTab('vars', document.querySelector('#settings-panel button'));
    } else {
      p.style.display = 'none';
    }
  }

  function hideSettings() {
    document.getElementById('settings-panel').style.display = 'none';
  }

  function _loadSettingsFromCol() {
    if (!_currentCol) return;
    // Variables
    const tbody = document.getElementById('vars-tbody');
    tbody.innerHTML = '';
    const vars = _currentCol.variables || [];
    if (vars.length) {
      vars.forEach(v => _addVarRowData(v.key, v.value, v.description || ''));
    }
    // Auth
    const authSel = document.getElementById('col-auth-type');
    if (authSel) { authSel.value = _currentCol.auth_type || 'none'; onColAuthChange(); }
    setTimeout(() => {
      const av = document.getElementById('col-auth-value');
      if (av) av.value = _currentCol.auth_token || '';
    }, 60);
    // Scripts
    document.getElementById('col-pre-script').value   = _currentCol.pre_request_script || '';
    document.getElementById('col-tests-script').value = _currentCol.tests_script || '';
  }

  function showSettingsTab(name, btn) {
    document.querySelectorAll('.settings-tab').forEach(t => t.style.display = 'none');
    document.getElementById(`stab-${name}`).style.display = '';
    document.querySelectorAll('#settings-panel > div:first-child button').forEach(b => {
      b.style.background = b === btn ? 'var(--accent-dim)' : '';
      b.style.color      = b === btn ? 'var(--accent)'     : '';
    });
  }

  function onColAuthChange() {
    const type = document.getElementById('col-auth-type')?.value || 'none';
    const box  = document.getElementById('col-auth-fields');
    if (!box) return;
    const tpls = {
      bearer: `<div class="form-group"><label class="label">Token</label><input id="col-auth-value" class="input input-mono" placeholder="eyJ…"/></div>`,
      basic:  `<div class="form-group"><label class="label">Base64</label><input id="col-auth-value" class="input input-mono"/></div>`,
      apikey: `<div class="grid2" style="gap:.5rem">
        <div class="form-group"><label class="label">Header</label><input id="col-auth-key-name" class="input" value="X-API-Key"/></div>
        <div class="form-group"><label class="label">Value</label><input id="col-auth-value" class="input input-mono"/></div></div>`,
      none:   '',
    };
    box.innerHTML = tpls[type] || '';
  }

  async function saveSettings() {
    if (!_currentColId) return;
    // Collect variables
    const vars = [];
    document.querySelectorAll('#vars-tbody tr').forEach(tr => {
      const key = tr.querySelector('.var-key')?.value?.trim();
      const val = tr.querySelector('.var-val')?.value || '';
      const desc= tr.querySelector('.var-desc')?.value || '';
      if (key) vars.push({ key, value: val, description: desc });
    });

    const authType  = document.getElementById('col-auth-type')?.value  || 'none';
    const authToken = document.getElementById('col-auth-value')?.value || '';
    const authKey   = document.getElementById('col-auth-key-name')?.value || 'X-API-Key';

    const payload = {
      name:               _currentCol.name,
      description:        _currentCol.description || '',
      auth_type:          authType,
      auth_token:         authToken,
      auth_key_name:      authKey,
      variables:          vars,
      pre_request_script: document.getElementById('col-pre-script')?.value   || '',
      tests_script:       document.getElementById('col-tests-script')?.value || '',
    };

    const data = await apiFetch(`/api/collections/${_currentColId}`, { body: payload });
    if (data.ok) {
      Toast.success('Settings saved ✓');
      _currentCol = { ..._currentCol, ...payload };
      hideSettings();
    } else Toast.error(data.error || 'Save failed');
  }

  /* ── Variables ──────────────────────────────────────────────── */
  function addVarRow() { _addVarRowData('', '', ''); }

  function _addVarRowData(key, value, desc) {
    const tbody = document.getElementById('vars-tbody');
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="width:26px"><input type="checkbox" class="kv-check" checked/></td>
      <td><input class="kv-key var-key" value="${_esc(key)}" placeholder="variableName"/></td>
      <td><input class="kv-val var-val" value="${_esc(value)}" placeholder="value"/></td>
      <td><input class="kv-val var-desc" value="${_esc(desc)}" placeholder="description"/></td>
      <td style="width:28px"><button class="kv-rm" onclick="this.closest('tr').remove()">✕</button></td>`;
    tbody.appendChild(tr);
  }

  /* ── Collection CRUD ────────────────────────────────────────── */
  async function createCollection() {
    const name = prompt('Collection name:');
    if (!name?.trim()) return;
    const data = await apiFetch('/api/collections', { body: { name: name.trim() } });
    if (data.ok) {
      Toast.success(`Created: ${name}`);
      location.reload();
    } else Toast.error(data.error || 'Failed');
  }

  async function deleteCollection() {
    if (!_currentColId) return;
    if (!confirm(`Delete "${_currentCol?.name}" and all its requests?`)) return;
    const data = await apiFetch(`/api/collections/${_currentColId}/delete`, { body: {} });
    if (data.ok) { Toast.success('Deleted'); location.reload(); }
    else Toast.error(data.error || 'Failed');
  }

  async function duplicateCollection() {
    if (!_currentColId) return;
    const data = await apiFetch(`/api/collections/${_currentColId}/duplicate`, { body: {} });
    if (data.ok) { Toast.success('Duplicated'); location.reload(); }
    else Toast.error(data.error || 'Failed');
  }

  async function exportCollection() {
    if (!_currentColId) return;
    const resp = await fetch(`/api/collections/${_currentColId}/export`);
    const data = await resp.json();
    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `${(_currentCol?.name||'collection').replace(/\s+/g,'-')}.json`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
    Toast.success('Exported as JSON');
  }

  /* ── Collection Runner ──────────────────────────────────────── */
  async function runCollection() {
    if (!_currentColId) return;
    // Make sure requests are loaded
    if (!_requests.length) {
      const data = await apiFetch(`/api/collections/${_currentColId}`);
      if (data.ok) _requests = data.requests;
    }
    document.getElementById('runner-col-name').textContent = _currentCol?.name || '';
    document.getElementById('runner-config').style.display  = '';
    document.getElementById('runner-results').style.display = 'none';
    _renderRunnerList();
    document.getElementById('runner-modal').style.display = 'block';
  }

  function closeRunner() {
    document.getElementById('runner-modal').style.display = 'none';
  }

  function _renderRunnerList() {
    const list = document.getElementById('runner-req-list');
    if (!list) return;
    list.innerHTML = _requests.map((r, i) => `
      <label style="display:flex;align-items:center;gap:.6rem;padding:.45rem .75rem;border-bottom:1px solid var(--border);cursor:pointer">
        <input type="checkbox" class="kv-check runner-req-chk" value="${r.id}" checked/>
        <span class="badge ${_mCls(r.method)} text-mono" style="font-size:.6rem;padding:.1rem .3rem">${r.method}</span>
        <span class="text-sm truncate">${_esc(r.name)}</span>
      </label>`).join('');
  }

  function selectAllRequests(checked) {
    document.querySelectorAll('.runner-req-chk').forEach(c => c.checked = checked);
  }

  async function startRun() {
    const selectedIds = Array.from(document.querySelectorAll('.runner-req-chk:checked')).map(c => parseInt(c.value));
    if (!selectedIds.length) { Toast.error('Select at least one request'); return; }

    const iterations = parseInt(document.getElementById('runner-iterations')?.value || 1);
    const btn = document.getElementById('runner-start-btn');
    btn.disabled = true; btn.textContent = '⏳ Running…';

    document.getElementById('runner-results').style.display = '';
    document.getElementById('runner-summary').innerHTML     = '<div style="grid-column:1/-1;color:var(--text3);text-align:center">Running…</div>';
    document.getElementById('runner-result-rows').innerHTML = '';

    let allResults = [];
    let summary    = null;

    for (let i = 0; i < iterations; i++) {
      const data = await apiFetch(`/api/collections/${_currentColId}/run`, {
        body: { request_ids: selectedIds },
      });
      if (!data.ok) { Toast.error(data.error || 'Run failed'); break; }
      allResults = allResults.concat(data.results);
      summary = data.summary;
      // Accumulate across iterations
      if (iterations > 1) {
        summary.total_requests  *= iterations;
        summary.request_passed = allResults.filter(r => r.request_passed).length;
        summary.request_failed = allResults.filter(r => !r.request_passed && !r.skipped).length;
        summary.pass_rate = Math.round(summary.request_passed / summary.total_requests * 100 * 10) / 10;
      }
    }

    _runnerReport = { summary, results: allResults };
    _renderRunnerResults(summary, allResults);
    btn.disabled = false; btn.textContent = '▶ Run';
  }

  function _renderRunnerResults(summary, results) {
    if (!summary) return;
    const summaryEl = document.getElementById('runner-summary');
    const rr = summary.request_failed > 0;
    summaryEl.innerHTML = `
      <div class="stat-card"><div class="stat-label">Requests</div><div class="stat-val c-blue">${summary.total_requests}</div></div>
      <div class="stat-card"><div class="stat-label">Passed</div><div class="stat-val c-green">${summary.request_passed}</div></div>
      <div class="stat-card"><div class="stat-label">Failed</div><div class="stat-val ${rr?'c-red':'c-green'}">${summary.request_failed}</div></div>
      <div class="stat-card"><div class="stat-label">Tests</div><div class="stat-val c-purple">${summary.total_tests}</div></div>
      <div class="stat-card"><div class="stat-label">Pass Rate</div><div class="stat-val ${summary.pass_rate>=80?'c-green':summary.pass_rate>=50?'c-yellow':'c-red'}">${summary.pass_rate}%</div></div>
      <div class="stat-card"><div class="stat-label">Total Time</div><div class="stat-val text-muted">${fmtMs(summary.total_time_ms)}</div></div>`;

    const rowsEl = document.getElementById('runner-result-rows');
    rowsEl.innerHTML = results.map((r, i) => {
      const passed = r.request_passed;
      const icon   = r.skipped ? '⏭' : passed ? '✅' : '❌';
      const tests  = r.tests || [];
      const testHtml = tests.length ? tests.map(t =>
        `<div style="padding:.2rem .5rem .2rem 1.5rem;font-size:.72rem;color:${t.passed?'var(--green)':'var(--red)'}">
          ${t.passed?'✓':'✗'} ${_esc(t.name)} ${t.error?`<span style="color:var(--text3)">(${_esc(t.error)})</span>`:''}
        </div>`).join('') : '';
      const consoleLogs = (r.console||[]).length ?
        `<div style="padding:.3rem .5rem .3rem 1rem;font-size:.7rem;color:var(--text3)">
          ${r.console.map(l=>`<div>[${l.level}] ${_esc(l.msg)}</div>`).join('')}</div>` : '';
      return `
        <div style="border:1px solid var(--border);border-radius:var(--radius);margin-bottom:.5rem;overflow:hidden">
          <div style="padding:.5rem .9rem;display:flex;align-items:center;gap:.75rem;background:var(--bg2);cursor:pointer"
               onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display?'':'block'">
            <span style="font-size:1rem">${icon}</span>
            <span class="badge ${_mCls(r.method)} text-mono" style="font-size:.63rem">${r.method}</span>
            <span class="text-sm fw6 truncate" style="flex:1">${_esc(r.name)}</span>
            <span class="${statusClass(r.status)} fw6 text-sm">${r.status||'—'}</span>
            <span class="text-muted text-sm">${fmtMs(r.response_ms)}</span>
            ${tests.length ? `<span class="badge ${tests.every(t=>t.passed)?'bg-green':'bg-red'} text-xs">${tests.filter(t=>t.passed).length}/${tests.length} tests</span>` : ''}
          </div>
          <div style="display:none">
            ${r.error ? `<div style="padding:.4rem .9rem;color:var(--red);font-size:.78rem">Error: ${_esc(r.error)}</div>` : ''}
            ${testHtml}
            ${consoleLogs}
            ${r.body ? `<details style="padding:.3rem .9rem"><summary style="cursor:pointer;font-size:.75rem;color:var(--text3)">Response Body</summary><pre style="font-size:.72rem;font-family:var(--mono);white-space:pre-wrap;max-height:150px;overflow-y:auto">${_esc((r.body||'').slice(0,2000))}</pre></details>` : ''}
          </div>
        </div>`;
    }).join('');
  }

  function resetRunner() {
    document.getElementById('runner-config').style.display  = '';
    document.getElementById('runner-results').style.display = 'none';
    _renderRunnerList();
  }

  function downloadReport() {
    if (!_runnerReport) return;
    const json = JSON.stringify(_runnerReport, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href = url; a.download = `collection-report-${Date.now()}.json`;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
    Toast.success('Report downloaded');
  }

  /* ── Utilities ──────────────────────────────────────────────── */
  function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function _mCls(m) {
    const map = {GET:'bg-blue',POST:'bg-green',PUT:'bg-yellow',PATCH:'bg-orange',DELETE:'bg-red'};
    return map[m] || 'bg-gray';
  }

  return {
    init, openCollection, openRequest, newRequest, saveRequest, sendRequest,
    deleteRequest, setReqBodyType, showReqTab, onReqAuthChange, showRespTab,
    createCollection, deleteCollection, duplicateCollection, exportCollection,
    showSettings, hideSettings, showSettingsTab, saveSettings, onColAuthChange,
    addVarRow, runCollection, closeRunner, startRun, selectAllRequests,
    resetRunner, downloadReport,
  };
})();

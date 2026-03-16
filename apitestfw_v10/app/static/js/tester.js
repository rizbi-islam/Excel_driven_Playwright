/**
 * tester.js — Full API Tester + Collections logic.
 */

/* ═══════════════════════════════════════════════════════════════
   TESTER
   ═══════════════════════════════════════════════════════════════ */
const Tester = (() => {
  let _lastResult  = null;
  let _lastPayload = null;

  function init() {
    document.getElementById('url-input')?.focus();
  }

  /* ── Sidebar tab ──────────────────────────────────────────── */
  function showSidebar(name, btn) {
    document.getElementById('sidebar-history').style.display    = name === 'history'     ? 'flex' : 'none';
    document.getElementById('sidebar-collections').style.display = name === 'collections' ? 'flex' : 'none';
    document.querySelectorAll('.tester-sidebar button[id^="tab-"]').forEach(b => {
      b.style.background = b === btn ? 'var(--accent-dim)' : '';
      b.style.color      = b === btn ? 'var(--accent)'     : '';
    });
    if (name === 'collections') CollectionPanel.load();
  }

  /* ── Request tab ──────────────────────────────────────────── */
  function showTab(name, el) {
    document.querySelectorAll('.req-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    el.classList.add('active');
    document.getElementById(`panel-${name}`)?.classList.add('active');
  }

  /* ── Auth fields ──────────────────────────────────────────── */
  function onAuthChange() {
    const type = document.getElementById('auth-type')?.value || 'none';
    const box  = document.getElementById('auth-fields');
    if (!box) return;
    const tpls = {
      bearer: `<div class="form-group"><label class="label">Bearer Token</label>
        <input id="auth-value" class="input input-mono" placeholder="eyJhbGc…"/></div>`,
      basic:  `<div class="form-group"><label class="label">Base64 Credentials</label>
        <input id="auth-value" class="input input-mono" placeholder="dXNlcjpwYXNz"/></div>`,
      apikey: `<div class="grid2"><div class="form-group"><label class="label">Header Name</label>
        <input id="auth-key-name" class="input" value="X-API-Key"/></div>
        <div class="form-group"><label class="label">Value</label>
        <input id="auth-value" class="input input-mono" placeholder="your-key"/></div></div>`,
    };
    box.innerHTML = tpls[type] || '';
  }

  /* ── Body type ────────────────────────────────────────────── */
  function setBodyType(type, el) {
    document.querySelectorAll('.body-type-btn').forEach(b => b.classList.remove('active'));
    el?.classList.add('active');

    // Hide all body panels
    document.getElementById('body-none-msg')?.style && (document.getElementById('body-none-msg').style.display = 'none');
    document.getElementById('body-textarea-wrap')?.style && (document.getElementById('body-textarea-wrap').style.display = 'none');
    document.getElementById('body-form-wrap')?.style && (document.getElementById('body-form-wrap').style.display = 'none');
    document.getElementById('body-multipart-wrap')?.style && (document.getElementById('body-multipart-wrap').style.display = 'none');

    if (type === 'none') {
      document.getElementById('body-none-msg').style.display = '';
    } else if (type === 'form' || type === 'urlencoded') {
      document.getElementById('body-form-wrap').style.display = '';
      if (window.kvBodyForm && !document.querySelector('#body-form-tbody tr')) window.kvBodyForm.addRow();
    } else if (type === 'multipart') {
      document.getElementById('body-multipart-wrap').style.display = '';
      if (window.kvBodyMulti && !document.querySelector('#body-multipart-tbody tr')) window.kvBodyMulti.addRow();
    } else {
      const area = document.getElementById('body-area');
      document.getElementById('body-textarea-wrap').style.display = '';
      const ph = {
        json:     '{\n  "key": "value"\n}',
        xml:      '<root><item>value</item></root>',
        graphql:  '{ users { id name email } }',
        raw:      'Plain text body',
      };
      if (area) area.placeholder = ph[type] || '';
    }
  }

  /* ── Env quick-fill ───────────────────────────────────────── */
  function fillFromEnv(sel) {
    const base = sel.value;
    if (base) {
      const u = document.getElementById('url-input');
      if (u && !u.value) u.value = base;
    }
  }

  /* ── Build request payload ────────────────────────────────── */
  function _payload() {
    const method    = document.getElementById('method-sel')?.value  || 'GET';
    const url       = (document.getElementById('url-input')?.value  || '').trim();
    const authType  = document.getElementById('auth-type')?.value   || 'none';
    const authValue = document.getElementById('auth-value')?.value  || '';
    const authKey   = document.getElementById('auth-key-name')?.value || 'X-API-Key';
    const bodyType  = document.querySelector('.body-type-btn.active')?.dataset.type || 'none';
    const timeout   = parseInt(document.getElementById('timeout-inp')?.value || '30', 10);

    // Build body based on active type
    let body = null;
    if (bodyType === 'form' || bodyType === 'urlencoded') {
      body = window.kvBodyForm?.getDict() || {};
      if (!Object.keys(body).length) body = null;
    } else if (bodyType === 'multipart') {
      body = window.kvBodyMulti?.getDict() || {};
      if (!Object.keys(body).length) body = null;
    } else if (bodyType !== 'none') {
      const raw = (document.getElementById('body-area')?.value || '').trim();
      if (raw) {
        if (bodyType === 'json') {
          try   { body = JSON.parse(raw); }
          catch { body = raw; }
        } else {
          body = raw;
        }
      }
    }

    return {
      method, url,
      headers:          window.kvHeaders?.getDict() || {},
      params:           window.kvParams?.getDict()  || {},
      body_type:        bodyType,
      body,
      auth_type:        authType,
      auth_value:       authValue,
      auth_key_name:    authKey,
      timeout,
      follow_redirects: true,
    };
  }

  /* ── Send ─────────────────────────────────────────────────── */
  async function send() {
    const payload = _payload();
    if (!payload.url) { Toast.error('URL is required'); return; }
    _setLoading(true);
    _clearResp();
    try {
      const data = await apiFetch('/api/send-request', { body: payload });
      _lastResult  = data;
      _lastPayload = payload;
      _renderResp(data);
      _runTestsScript(data);
    } catch (e) {
      Toast.error(`Error: ${e.message}`);
      _setLoading(false);
    }
  }

  /* ── Batch ────────────────────────────────────────────────── */
  async function batchSend() {
    const payload = _payload();
    if (!payload.url) { Toast.error('URL is required'); return; }
    _setLoading(true, 'Running batch…');
    _clearResp();
    try {
      const data = await apiFetch('/api/batch-send', { body: payload });
      _setLoading(false);
      if (!data.ok) { Toast.error(data.error || 'Batch failed'); return; }
      _renderBatch(data.results);
      Toast.success(`Batch: ${data.count} requests sent`);
    } catch (e) {
      _setLoading(false);
      Toast.error(e.message);
    }
  }

  /* ── Render response ──────────────────────────────────────── */
  function _renderResp(data) {
    _setLoading(false);
    const sc = data.status || 0;

    const codeEl = document.getElementById('resp-status-code');
    if (codeEl) {
      codeEl.textContent = `${sc} ${data.status_text || ''}`;
      codeEl.className   = `resp-status ${statusClass(sc)}`;
    }
    const msEl   = document.getElementById('resp-ms');
    if (msEl)   msEl.textContent = fmtMs(data.response_ms);
    const szEl   = document.getElementById('resp-size');
    if (szEl)   szEl.textContent = _fmtSize(data.size);
    const errEl  = document.getElementById('resp-error');
    if (errEl)  errEl.textContent = data.error ? `⚠ ${data.error}` : '';

    const bodyEl = document.getElementById('resp-body');
    if (bodyEl) { bodyEl.style.color = 'var(--text1)'; bodyEl.textContent = data.body || '(empty body)'; }

    const hdrsEl = document.getElementById('resp-headers-view');
    if (hdrsEl && data.resp_headers) {
      hdrsEl.textContent = Object.entries(data.resp_headers).map(([k,v]) => `${k}: ${v}`).join('\n') || '(none)';
    }

    const saveBtn = document.getElementById('save-case-btn');
    if (saveBtn) saveBtn.style.display = '';

    const expEl = document.getElementById('save-expected');
    if (expEl) expEl.value = sc || 200;
  }

  function _renderBatch(results) {
    _setLoading(false);
    const bodyEl = document.getElementById('resp-body');
    if (!bodyEl) return;
    bodyEl.style.color = 'var(--text1)';
    const codeEl = document.getElementById('resp-status-code');
    if (codeEl) {
      const passed = results.filter(r => r.status < 400).length;
      codeEl.textContent = `Batch: ${passed}/${results.length} passed`;
      codeEl.className   = '';
    }
    const rows = results.map(r => {
      const pStr = JSON.stringify(r.batch_params || r.batch_body || {}).slice(0, 70);
      return `<tr>
        <td style="padding:.3rem .5rem;border-bottom:1px solid var(--border);font-family:var(--mono);font-size:.72rem">${_esc(pStr)}</td>
        <td style="padding:.3rem .5rem;border-bottom:1px solid var(--border)" class="${statusClass(r.status)} fw6">${r.status}</td>
        <td style="padding:.3rem .5rem;border-bottom:1px solid var(--border);color:var(--text3);font-size:.72rem">${fmtMs(r.response_ms)}</td>
      </tr>`;
    }).join('');
    bodyEl.innerHTML = `<table style="width:100%;border-collapse:collapse">
      <thead><tr>
        <th style="padding:.28rem .5rem;font-size:.67rem;color:var(--text3);border-bottom:1px solid var(--border);text-align:left">Params/Body</th>
        <th style="padding:.28rem .5rem;font-size:.67rem;color:var(--text3);border-bottom:1px solid var(--border);text-align:left">Status</th>
        <th style="padding:.28rem .5rem;font-size:.67rem;color:var(--text3);border-bottom:1px solid var(--border);text-align:left">Time</th>
      </tr></thead><tbody>${rows}</tbody></table>`;
    const saveBtn = document.getElementById('save-case-btn');
    if (saveBtn) saveBtn.style.display = '';
  }

  function showRespTab(name, el) {
    document.querySelectorAll('.resp-tab-btn').forEach(b => {
      b.style.background = '';
      b.style.color = '';
    });
    if (el) { el.style.background = 'var(--bg3)'; }
    const bodyEl  = document.getElementById('resp-body');
    const hdrsEl  = document.getElementById('resp-headers-view');
    const testsEl = document.getElementById('resp-tests-view');
    if (bodyEl)  bodyEl.style.display  = name === 'body'    ? '' : 'none';
    if (hdrsEl)  hdrsEl.style.display  = name === 'headers' ? '' : 'none';
    if (testsEl) testsEl.style.display = name === 'tests'   ? '' : 'none';
  }

  /* ── Save modal ───────────────────────────────────────────── */
  function showSaveModal() {
    if (!_lastPayload?.url) { Toast.error('Send a request first'); return; }
    const modal = document.getElementById('save-modal');
    if (modal) modal.style.display = 'flex';
    const nameEl = document.getElementById('save-name');
    if (nameEl) { nameEl.value = ''; nameEl.focus(); }
  }
  function hideSaveModal() {
    document.getElementById('save-modal').style.display    = 'none';
    document.getElementById('col-save-modal').style.display = 'none';
  }

  async function saveAsCase() {
    const name = (document.getElementById('save-name')?.value || '').trim();
    if (!name) { Toast.error('Name is required'); return; }
    if (!_lastPayload?.url) { Toast.error('No request to save'); return; }
    const data = await apiFetch('/api/tester/save-as-case', { body: {
      name,
      url:             _lastPayload.url,
      method:          _lastPayload.method,
      headers:         _lastPayload.headers,
      body:            _lastPayload.body,
      body_type:       _lastPayload.body_type,
      params:          _lastPayload.params,
      auth_type:       _lastPayload.auth_type,
      auth_token:      _lastPayload.auth_value,
      expected_status: parseInt(document.getElementById('save-expected')?.value || '200'),
      description:     document.getElementById('save-desc')?.value || '',
      sheet_type:      document.getElementById('save-type')?.value || 'regression',
      test_type:       document.getElementById('save-type')?.value || 'regression',
      api_id:          document.getElementById('save-api')?.value  || null,
    }});
    if (data.ok) { Toast.success('Saved to library ✓'); hideSaveModal(); }
    else         Toast.error(data.error || 'Save failed');
  }

  /* ── Load request into tester ─────────────────────────────── */
  function loadRequest(req) {
    // Accepts either a history item (has .url) or a collection_request (has .url)
    document.getElementById('url-input').value = req.url || '';
    const methodEl = document.getElementById('method-sel');
    if (methodEl) methodEl.value = req.method || 'GET';

    const headers = req.headers || (req.request_data?.headers) || {};
    const params  = req.params  || (req.request_data?.params)  || {};
    const body    = req.body    || (req.request_data?.body);
    const btype   = req.body_type || req.request_data?.body_type || 'none';

    if (window.kvHeaders) window.kvHeaders.load(headers);
    if (window.kvParams)  window.kvParams.load(params);

    // Set body type
    const btn = document.querySelector(`.body-type-btn[data-type="${btype}"]`);
    if (btn) setBodyType(btype, btn);

    if (btype === 'form' || btype === 'urlencoded') {
      if (window.kvBodyForm && typeof body === 'object' && body) window.kvBodyForm.load(body);
    } else if (btype === 'multipart') {
      if (window.kvBodyMulti && typeof body === 'object' && body) window.kvBodyMulti.load(body);
    } else if (body && btype !== 'none') {
      const area = document.getElementById('body-area');
      if (area) area.value = typeof body === 'string' ? body : JSON.stringify(body, null, 2);
    }

    // Auth
    if (req.auth_type && req.auth_type !== 'none') {
      const authSel = document.getElementById('auth-type');
      if (authSel) { authSel.value = req.auth_type; onAuthChange(); }
      setTimeout(() => {
        const av = document.getElementById('auth-value');
        if (av) av.value = req.auth_token || '';
      }, 50);
    }
  }

  /* ── History ──────────────────────────────────────────────── */
  async function loadHistory(id, el) {
    document.querySelectorAll('.hist-item').forEach(i => i.classList.remove('active'));
    el?.classList.add('active');
    const data = await apiFetch(`/api/tester/history/${id}`);
    if (!data.ok || !data.item) return;
    loadRequest(data.item);
  }

  async function clearHistory() {
    if (!confirm('Clear all request history?')) return;
    const data = await apiFetch('/api/tester/history/clear', { body: {} });
    if (data.ok) {
      document.getElementById('history-list').innerHTML =
        '<div style="padding:1rem;color:var(--text3);font-size:.74rem;text-align:center">No history</div>';
      Toast.success('History cleared');
    }
  }

  /* ── Helpers ──────────────────────────────────────────────── */
  function clear() {
    document.getElementById('url-input').value = '';
    document.getElementById('method-sel').value = 'GET';
    window.kvParams?.clear();      window.kvParams?.addRow();
    window.kvHeaders?.clear();     window.kvHeaders?.addRow();
    window.kvBodyForm?.clear();
    window.kvBodyMulti?.clear();
    _clearResp();
    const bodyArea = document.getElementById('body-area');
    if (bodyArea) bodyArea.value = '';
    const noneBtn = document.querySelector('.body-type-btn[data-type="none"]');
    if (noneBtn) setBodyType('none', noneBtn);
    _lastResult = null; _lastPayload = null;
    const saveBtn = document.getElementById('save-case-btn');
    if (saveBtn) saveBtn.style.display = 'none';
  }

  function copyBody() {
    const el = document.getElementById('resp-body');
    if (!el) return;
    navigator.clipboard.writeText(el.textContent || '').then(() => Toast.success('Copied')).catch(() => Toast.error('Copy failed'));
  }

  function _clearResp() {
    ['resp-status-code','resp-ms','resp-size','resp-error'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '';
    });
    const bodyEl = document.getElementById('resp-body');
    if (bodyEl) { bodyEl.style.color = 'var(--text3)'; bodyEl.textContent = 'Send a request to see the response here.'; bodyEl.style.display = ''; }
    const hdrsEl = document.getElementById('resp-headers-view');
    if (hdrsEl) { hdrsEl.textContent = ''; hdrsEl.style.display = 'none'; }
    const testEl = document.getElementById('resp-tests-view');
    if (testEl) testEl.style.display = 'none';
    const tlist  = document.getElementById('resp-tests-list');
    if (tlist)  tlist.innerHTML = '';
    const badge  = document.getElementById('resp-tests-badge');
    if (badge)  badge.style.display = 'none';
  }

  function _setLoading(on, label = '⏳ Sending…') {
    const btn  = document.getElementById('send-btn');
    const spin = document.getElementById('send-spin');
    if (btn)  { btn.disabled = on; btn.textContent = on ? label : '▶ Send'; }
    if (spin) spin.style.display = on ? '' : 'none';
  }

  function _fmtSize(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // Expose loadRequest for CollectionPanel
  /* ── Post-request tests script ─────────────────────────────── */
  function _runTestsScript(resp) {
    const script = document.getElementById('tests-script')?.value?.trim();
    const container = document.getElementById('tests-results');
    if (!container) return;
    if (!script) { container.innerHTML = ''; return; }

    const results = [];
    const logs    = [];

    // Minimal pm object in JS (mirrors Python sandbox)
    const pm = {
      response: {
        code:         resp.status || 0,
        status:       resp.status_text || '',
        responseTime: resp.response_ms || 0,
        headers:      resp.resp_headers || {},
        json: () => { try { return JSON.parse(resp.body || '{}'); } catch { return {}; } },
        text: () => resp.body || '',
      },
      variables: (() => {
        const store = {};
        return {
          get: (k, d=null) => store[k] ?? d,
          set: (k, v) => { store[k] = v; },
          has: (k) => k in store,
          unset: (k) => { delete store[k]; },
        };
      })(),
      expect: (val) => ({
        to_equal:     (ex) => { if (val !== ex) throw new Error(`Expected ${JSON.stringify(ex)}, got ${JSON.stringify(val)}`); },
        to_include:   (s)  => { if (!String(val).includes(String(s))) throw new Error(`Expected to include ${JSON.stringify(s)}`); },
        to_be_truthy: ()   => { if (!val) throw new Error(`Expected truthy, got ${JSON.stringify(val)}`); },
        to_be_below:  (n)  => { if (!(val < n))  throw new Error(`Expected < ${n}, got ${val}`); },
        to_be_above:  (n)  => { if (!(val > n))  throw new Error(`Expected > ${n}, got ${val}`); },
        // aliases
        equal: function(ex) { this.to_equal(ex); },
        include: function(s) { this.to_include(s); },
        eql: function(ex) { this.to_equal(ex); },
      }),
      test: (name, fn) => {
        try {
          fn();
          results.push({ name, passed: true, error: null });
        } catch(e) {
          results.push({ name, passed: false, error: e.message });
        }
      },
    };
    const console_ = {
      log:   (...a) => logs.push({ level: 'log',  msg: a.join(' ') }),
      warn:  (...a) => logs.push({ level: 'warn', msg: a.join(' ') }),
      error: (...a) => logs.push({ level: 'error',msg: a.join(' ') }),
    };

    try {
      // Simple transpile: to_equal -> .to_equal() etc already work since we use JS syntax
      const fn = new Function('pm', 'console', script);
      fn(pm, console_);
    } catch(e) {
      logs.push({ level: 'error', msg: 'Script error: ' + e.message });
    }

    // Render results
    const badge = document.getElementById('tests-badge');
    if (badge) {
      badge.textContent = results.length;
      badge.style.display = results.length ? '' : 'none';
      badge.style.background = results.every(r=>r.passed) ? 'var(--green)' : 'var(--red)';
      badge.style.color = '#fff';
    }

    if (!results.length && !logs.length) { container.innerHTML = ''; return; }

    let html = '<div style="border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;margin-top:.3rem">';
    if (results.length) {
      html += '<div style="padding:.4rem .75rem;background:var(--bg2);font-size:.72rem;font-weight:600;color:var(--text3);border-bottom:1px solid var(--border)">Test Results</div>';
      results.forEach(r => {
        const c = r.passed ? 'var(--green)' : 'var(--red)';
        const i = r.passed ? '✓' : '✗';
        html += `<div style="padding:.35rem .75rem;font-size:.78rem;color:${c};border-bottom:1px solid var(--border)">
          ${i} <span style="color:var(--text1)">${_escHtml(r.name)}</span>
          ${r.error ? `<span style="color:var(--text3);font-size:.72rem"> — ${_escHtml(r.error)}</span>` : ''}
        </div>`;
      });
    }
    if (logs.length) {
      html += '<div style="padding:.4rem .75rem;background:var(--bg2);font-size:.72rem;font-weight:600;color:var(--text3);border-bottom:1px solid var(--border)">Console</div>';
      logs.forEach(l => {
        const lc = l.level === 'error' ? 'var(--red)' : l.level === 'warn' ? 'var(--yellow)' : 'var(--text3)';
        html += `<div style="padding:.3rem .75rem;font-size:.75rem;font-family:var(--mono);color:${lc};border-bottom:1px solid var(--border)">[${l.level}] ${_escHtml(l.msg)}</div>`;
      });
    }
    html += '</div>';
    container.innerHTML = html;

    // Auto-switch to tests tab if there are results
    const testsTab = document.querySelector('.req-tab[onclick*="tests"]');
    if (testsTab && (results.length || logs.length)) {
      // Don't force switch, just highlight badge
    }
  }

  function _escHtml(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return {
    init, send, batchSend, clear, copyBody,
    showTab, showSidebar, onAuthChange, setBodyType, fillFromEnv,
    loadHistory, clearHistory, loadRequest,
    showSaveModal, hideSaveModal, saveAsCase,
    showRespTab,
    getLastPayload: () => _lastPayload,
    getLastResult:  () => _lastResult,
  };
})();


/* ═══════════════════════════════════════════════════════════════
   COLLECTION PANEL
   ═══════════════════════════════════════════════════════════════ */
const CollectionPanel = (() => {
  let _collections = [];
  let _openColId   = null;

  async function load() {
    const data = await apiFetch('/api/collections');
    if (!data.ok) return;
    _collections = data.collections;
    _render();
  }

  function _render() {
    const list = document.getElementById('collections-list');
    if (!list) return;
    if (!_collections.length) {
      list.innerHTML = '<div style="padding:1rem;color:var(--text3);font-size:.74rem;text-align:center">No collections yet.<br>Type a name above and click +</div>';
      return;
    }
    list.innerHTML = _collections.map(c => `
      <div class="col-group" id="colg-${c.id}">
        <div class="col-group-header" onclick="CollectionPanel.toggle(${c.id})">
          <span style="font-size:.8rem">📁</span>
          <span class="fw6 text-sm truncate" style="flex:1">${_esc(c.name)}</span>
          <span class="text-muted text-xs">${c.request_count||0}</span>
          <button class="btn btn-ghost btn-xs c-red" style="margin-left:.25rem"
                  onclick="event.stopPropagation();CollectionPanel.deleteCol(${c.id})" title="Delete collection">🗑</button>
        </div>
        <div class="col-requests" id="colr-${c.id}" style="display:none"></div>
      </div>`).join('');
  }

  async function toggle(id) {
    const req  = document.getElementById(`colr-${id}`);
    const head = req?.previousElementSibling;
    if (!req) return;
    if (req.style.display !== 'none') {
      req.style.display = 'none'; return;
    }
    // Load requests
    const data = await apiFetch(`/api/collections/${id}`);
    if (!data.ok) return;
    req.style.display = '';
    if (!data.requests.length) {
      req.innerHTML = '<div style="padding:.5rem 1.5rem;color:var(--text3);font-size:.73rem">No requests yet</div>';
      return;
    }
    req.innerHTML = data.requests.map(r => `
      <div class="col-req-item" onclick="CollectionPanel.loadReq(${r.id})">
        <span class="hist-method m-${r.method}" style="font-size:.65rem;width:44px">${r.method}</span>
        <span class="truncate text-sm" style="flex:1">${_esc(r.name)}</span>
        <button class="btn btn-ghost btn-xs c-red"
                onclick="event.stopPropagation();CollectionPanel.deleteReq(${r.id},${id})" title="Remove">✕</button>
      </div>`).join('');
  }

  async function loadReq(rid) {
    const data = await apiFetch(`/api/collections/requests/${rid}`);
    if (!data.ok) return;
    Tester.loadRequest(data.request);
    Tester.showSidebar('history', document.getElementById('tab-hist'));
    Toast.info(`Loaded: ${data.request.name}`);
  }

  async function create() {
    const inp  = document.getElementById('new-col-name');
    const name = (inp?.value || '').trim();
    if (!name) { Toast.error('Enter a collection name'); return; }
    const data = await apiFetch('/api/collections', { body: { name } });
    if (data.ok) {
      Toast.success(`Collection "${name}" created`);
      inp.value = '';
      await load();
    } else Toast.error(data.error || 'Failed');
  }

  async function deleteCol(id) {
    if (!confirm('Delete this collection and all its requests?')) return;
    const data = await apiFetch(`/api/collections/${id}/delete`, { body: {} });
    if (data.ok) { Toast.success('Deleted'); await load(); }
    else Toast.error(data.error || 'Failed');
  }

  async function deleteReq(rid, colId) {
    const data = await apiFetch(`/api/collections/requests/${rid}/delete`, { body: {} });
    if (data.ok) { Toast.success('Removed'); toggle(colId); setTimeout(() => toggle(colId), 100); }
    else Toast.error(data.error || 'Failed');
  }

  /* ── Save current request to collection ─────────────────── */
  function showSaveToCollectionModal() {
    const p = Tester.getLastPayload();
    if (!p?.url) { Toast.error('Send a request first'); return; }
    Tester.hideSaveModal();
    // Populate collection picker
    const sel = document.getElementById('col-pick');
    if (sel) {
      sel.innerHTML = _collections.length
        ? _collections.map(c => `<option value="${c.id}">${_esc(c.name)}</option>`).join('')
        : '<option value="">No collections — create one first</option>';
    }
    const nameEl = document.getElementById('col-req-name');
    if (nameEl) nameEl.value = p.url;
    document.getElementById('col-save-modal').style.display = 'flex';
    nameEl?.focus();
  }

  async function saveToCollection() {
    const p   = Tester.getLastPayload();
    const colId = parseInt(document.getElementById('col-pick')?.value);
    const name  = (document.getElementById('col-req-name')?.value || '').trim();
    if (!p?.url)  { Toast.error('No request to save'); return; }
    if (!colId)   { Toast.error('Select a collection'); return; }
    if (!name)    { Toast.error('Name is required'); return; }
    const data = await apiFetch(`/api/collections/${colId}/requests`, {
      body: { name, ...p, auth_token: p.auth_value },
    });
    if (data.ok) {
      Toast.success(`Saved to collection ✓`);
      hideSaveModal();
      await load();
    } else Toast.error(data.error || 'Save failed');
  }

  function hideSaveModal() {
    document.getElementById('col-save-modal').style.display = 'none';
  }

  function open() {
    Tester.showSidebar('collections', document.getElementById('tab-cols'));
  }

  function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  return { load, toggle, loadReq, create, deleteCol, deleteReq, open, showSaveToCollectionModal, saveToCollection, hideSaveModal };
})();

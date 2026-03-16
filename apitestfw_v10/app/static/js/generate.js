/**
 * generate.js — Auto-generate test cases.
 * Step 1: Config (base URL, auth, cases per endpoint)
 * Step 2: Select test types
 * Step 3: Add endpoints with method/body/params
 * Step 4: Review per-type tab, toggle active, save to library or download Excel
 */
const Generate = (() => {
  let _analyses  = [];
  let _endpoints = [];
  let _baseUrl   = '';
  let _allCases  = {};  // { type: [{...case, _active:true}] }

  function init() {
    addRow();
  }

  function addRow() {
    const tbody = document.getElementById('ep-tbody');
    if (!tbody) return;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>
        <select class="select ep-method" style="font-size:.79rem;width:94px">
          <option>GET</option><option>POST</option><option>PUT</option>
          <option>PATCH</option><option>DELETE</option><option>HEAD</option>
        </select>
      </td>
      <td><input class="input ep-path" placeholder="/api/users" style="width:100%"/></td>
      <td><input class="input ep-name" placeholder="List users (optional)"/></td>
      <td><input class="input ep-expected" type="number" value="200" style="width:72px"/></td>
      <td>
        <select class="select ep-body-type" style="font-size:.78rem" onchange="_onEpBodyChange(this)">
          <option value="none">No body</option>
          <option value="json">JSON</option>
          <option value="form">form-urlencoded</option>
          <option value="multipart">form-data</option>
        </select>
      </td>
      <td>
        <textarea class="ep-body textarea" rows="2"
                  style="display:none;font-size:.73rem;width:100%;resize:vertical"
                  placeholder='{"key":"value"}'></textarea>
        <span class="ep-nobody text-muted text-xs">—</span>
      </td>
      <td><button class="kv-rm" onclick="this.closest('tr').remove()">✕</button></td>`;
    tbody.appendChild(tr);
    tr.querySelector('.ep-path')?.focus();
  }

  // Toggle body textarea when body type changes in endpoint row
  window._onEpBodyChange = function(sel) {
    const td   = sel.closest('tr').querySelector('td:nth-child(6)');
    const area = td.querySelector('.ep-body');
    const none = td.querySelector('.ep-nobody');
    const show = sel.value !== 'none';
    area.style.display = show ? '' : 'none';
    none.style.display = show ? 'none' : '';
  };

  function _collectEndpoints() {
    const eps = [];
    document.querySelectorAll('#ep-tbody tr').forEach(tr => {
      const path = tr.querySelector('.ep-path')?.value?.trim();
      if (!path) return;
      const btype = tr.querySelector('.ep-body-type')?.value || 'none';
      const bRaw  = tr.querySelector('.ep-body')?.value?.trim() || '';
      let body = null;
      if (btype !== 'none' && bRaw) {
        if (btype === 'json') { try { body = JSON.parse(bRaw); } catch { body = bRaw; } }
        else body = bRaw;
      }
      eps.push({
        method:          tr.querySelector('.ep-method')?.value || 'GET',
        path,
        name:            tr.querySelector('.ep-name')?.value?.trim() || '',
        expected_status: parseInt(tr.querySelector('.ep-expected')?.value || 200),
        body_type:       btype,
        body,
      });
    });
    return eps;
  }

  function _getSelectedTypes() {
    return Array.from(document.querySelectorAll('.type-check:checked')).map(c => c.value);
  }

  async function analyze() {
    _baseUrl   = (document.getElementById('base-url')?.value || '').trim().replace(/\/+$/, '');
    _endpoints = _collectEndpoints();
    const types      = _getSelectedTypes();
    const casesPerEp = parseInt(document.getElementById('cases-per-ep')?.value || 3);

    if (!_baseUrl)           { Toast.error('Base URL is required'); return; }
    if (!_endpoints.length)  { Toast.error('Add at least one endpoint'); return; }
    if (!types.length)       { Toast.error('Select at least one test type'); return; }

    const btn = document.getElementById('analyze-btn');
    btn.disabled = true; btn.textContent = '⏳ Analyzing…';

    // Probe all endpoints
    const probeData = await apiFetch('/api/generate/analyze', {
      body: {
        base_url:   _baseUrl,
        auth_type:  document.getElementById('auth-type')?.value  || 'none',
        auth_token: document.getElementById('auth-token')?.value || '',
        endpoints:  _endpoints,
      },
    });

    btn.disabled = false; btn.textContent = '🔍 Analyze & Generate Cases';

    if (!probeData.ok) { Toast.error(probeData.error || 'Analysis failed'); return; }
    _analyses = probeData.analyses;

    // Generate cases per type
    _allCases = {};
    let totalCases = 0;

    for (const type of types) {
      _allCases[type] = [];
      for (let epIdx = 0; epIdx < _endpoints.length; epIdx++) {
        const ep = _endpoints[epIdx];
        const an = _analyses[epIdx] || {};
        const generatedForEp = _generateCases(ep, an, type, casesPerEp);
        _allCases[type].push(...generatedForEp);
        totalCases += generatedForEp.length;
      }
    }

    document.getElementById('cases-count').textContent = `${totalCases} cases across ${types.length} type(s)`;
    _renderTypeTabs(types);
    document.getElementById('results-card').style.display = '';
    Toast.success(`Generated ${totalCases} cases — review and save`);
  }

  function _generateCases(ep, analysis, type, count) {
    const method    = ep.method || 'GET';
    const path      = ep.path;
    const name      = ep.name || path;
    const probeStatus = analysis.status || 200;
    const bodyS     = analysis.body_sample;
    const hasBody   = method !== 'GET' && method !== 'HEAD' && method !== 'DELETE';
    const body      = hasBody ? (ep.body || (bodyS && method !== 'GET' ? bodyS : null)) : null;
    const bodyType  = hasBody && body ? ep.body_type || 'json' : 'none';

    const base = {
      method, endpoint: path, body, body_type: bodyType,
      params: {}, headers: {},
      auth_type: document.getElementById('auth-type')?.value || 'none',
      auth_token: document.getElementById('auth-token')?.value || '',
      test_type: type, sheet_type: type, _active: true,
    };

    const cases = [];

    if (type === 'smoke') {
      cases.push({ ...base,
        name:            `[Smoke] ${name}`,
        expected_status: probeStatus,
        max_response_ms: 3000,
        description:     'Verify endpoint responds within acceptable time.',
      });
    }

    if (type === 'regression') {
      cases.push({ ...base,
        name:            `[Regression] ${name} — Happy Path`,
        expected_status: probeStatus,
        description:     'Verify successful response.',
      });
      // 404 case
      cases.push({ ...base,
        name:            `[Regression] ${name} — Not Found`,
        endpoint:        path.replace(/\/$/, '') + '/nonexistent_id_99999',
        expected_status: 404,
        body:            null, body_type: 'none',
        description:     'Verify 404 for unknown resource.',
      });
      // Unauthorized case (if auth is set)
      if (base.auth_type !== 'none') {
        cases.push({ ...base,
          name:            `[Regression] ${name} — Unauthorized`,
          expected_status: 401,
          auth_type:       'none', auth_token: '',
          description:     'Verify 401 when no credentials sent.',
        });
      }
      // Extra cases up to count
      if (count > 3 && method === 'POST' && body) {
        cases.push({ ...base,
          name:            `[Regression] ${name} — Empty Body`,
          expected_status: 400,
          body:            {},
          description:     'Verify 400 when required fields are missing.',
        });
      }
    }

    if (type === 'load') {
      cases.push({ ...base,
        name:            `[Load] ${name}`,
        expected_status: probeStatus,
        concurrency:     10, duration_sec: 30, max_response_ms: 2000,
        description:     'Load test: 10 concurrent threads for 30 seconds.',
      });
    }

    if (type === 'stress') {
      cases.push({ ...base,
        name:            `[Stress] ${name}`,
        expected_status: probeStatus,
        start_users:     1, peak_users: 50, ramp_sec: 60,
        description:     'Stress test: ramp from 1 → 50 users over 60 seconds.',
      });
    }

    if (type === 'security') {
      cases.push({ ...base,
        name:            `[Security] ${name}`,
        expected_status: probeStatus,
        check_types:     'sqli,xss,cors,auth_bypass,https,info_disclosure,rate_limit',
        description:     'Run all security checks.',
      });
    }

    return cases.slice(0, count);
  }

  /* ── Render tabs per type ────────────────────────────────────── */
  function _renderTypeTabs(types) {
    const tabsEl   = document.getElementById('type-tabs');
    const panelsEl = document.getElementById('type-panels');
    tabsEl.innerHTML   = '';
    panelsEl.innerHTML = '';

    types.forEach((type, i) => {
      const count = (_allCases[type] || []).length;
      // Tab button
      const btn = document.createElement('button');
      btn.className   = 'req-editor-tab' + (i === 0 ? ' active' : '');
      btn.textContent = `${type} (${count})`;
      btn.onclick     = () => {
        document.querySelectorAll('#type-tabs .req-editor-tab').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.type-panel').forEach(p => p.style.display = 'none');
        btn.classList.add('active');
        document.getElementById(`tp-${type}`).style.display = '';
      };
      tabsEl.appendChild(btn);

      // Panel
      const panel = document.createElement('div');
      panel.id          = `tp-${type}`;
      panel.className   = 'type-panel';
      panel.style.display = i === 0 ? '' : 'none';
      panel.innerHTML   = _renderCaseTable(type);
      panelsEl.appendChild(panel);
    });
  }

  function _renderCaseTable(type) {
    const cases = _allCases[type] || [];
    if (!cases.length) return '<div class="empty-state"><div class="empty-text">No cases generated.</div></div>';

    const rows = cases.map((c, idx) => `
      <tr id="gen-row-${type}-${idx}" style="opacity:${c._active?1:.45}">
        <td style="text-align:center">
          <button class="btn btn-ghost btn-xs" style="font-size:.95rem;padding:.15rem .3rem"
                  data-active="${c._active?1:0}"
                  onclick="Generate.toggleCase('${type}',${idx},this)"
                  title="${c._active?'Active — click to skip':'Skipped — click to activate'}">
            ${c._active?'✅':'⏭'}
          </button>
        </td>
        <td>
          <span class="badge ${c.method==='GET'?'bg-blue':c.method==='POST'?'bg-green':c.method in ['PUT','PATCH']?'bg-yellow':'bg-red'} text-mono">
            ${c.method}
          </span>
        </td>
        <td>
          <input class="input" style="font-size:.76rem;width:100%" value="${_esc(c.name)}"
                 oninput="Generate.updateCaseName('${type}',${idx},this.value)"/>
        </td>
        <td class="text-mono text-sm">${_esc(c.endpoint)}</td>
        <td>
          <input class="input" type="number" style="width:70px;font-size:.76rem"
                 value="${c.expected_status||200}"
                 oninput="Generate.updateCaseExpected('${type}',${idx},this.value)"/>
        </td>
        <td class="text-muted text-sm">${_esc(c.description||'')}</td>
      </tr>`).join('');

    return `<div class="tbl-wrap" style="padding:0">
      <table>
        <thead><tr>
          <th style="width:42px;text-align:center">Run</th>
          <th style="width:75px">Method</th>
          <th>Name</th>
          <th>Endpoint</th>
          <th style="width:90px">Expected</th>
          <th>Description</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  }

  /* ── Toggle / update ─────────────────────────────────────────── */
  function toggleCase(type, idx, btn) {
    const c = _allCases[type][idx];
    if (!c) return;
    c._active = !c._active;
    btn.dataset.active = c._active ? 1 : 0;
    btn.textContent    = c._active ? '✅' : '⏭';
    btn.title          = c._active ? 'Active — click to skip' : 'Skipped — click to activate';
    const row = document.getElementById(`gen-row-${type}-${idx}`);
    if (row) row.style.opacity = c._active ? 1 : 0.45;
  }

  function updateCaseName(type, idx, val) {
    if (_allCases[type]?.[idx]) _allCases[type][idx].name = val;
  }

  function updateCaseExpected(type, idx, val) {
    if (_allCases[type]?.[idx]) _allCases[type][idx].expected_status = parseInt(val) || 200;
  }

  /* ── Save to library ─────────────────────────────────────────── */
  async function saveToLibrary() {
    const allActive = [];
    for (const type of Object.keys(_allCases)) {
      allActive.push(...(_allCases[type] || []).filter(c => c._active));
    }
    if (!allActive.length) { Toast.error('No active cases to save'); return; }

    // Clean up internal fields
    const toSave = allActive.map(c => {
      const { _active, ...clean } = c;
      return clean;
    });

    const data = await apiFetch('/api/generate/save', {
      body: { base_url: _baseUrl, cases: toSave },
    });

    if (data.ok) Toast.success(`Saved ${data.saved} cases to library ✓`);
    else         Toast.error(data.error || 'Save failed');
  }

  /* ── Download Excel ──────────────────────────────────────────── */
  async function downloadExcel() {
    if (!_endpoints.length) { Toast.error('Run analysis first'); return; }
    const data = await apiFetch('/api/generate/excel', {
      body: { base_url: _baseUrl, endpoints: _endpoints, analyses: _analyses },
    });
    if (!data.ok) { Toast.error(data.error || 'Download failed'); return; }
    downloadBase64(data.data, data.filename,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    Toast.success(`Downloaded ${data.filename}`);
  }

  function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { init, addRow, analyze, toggleCase, updateCaseName, updateCaseExpected, saveToLibrary, downloadExcel };
})();

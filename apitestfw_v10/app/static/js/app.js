/**
 * app.js — Global utilities shared across all pages.
 * Toast notifications, KV key-value editors, API helpers.
 */

/* ── Toast ─────────────────────────────────────────────────────── */
const Toast = (() => {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warn: '⚠️' };

  function show(msg, type = 'info', ms = 3500) {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.innerHTML = `<span>${icons[type] || ''}</span><span>${msg}</span>`;
    container.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transform = 'translateX(110%)'; el.style.transition = '.2s'; setTimeout(() => el.remove(), 250); }, ms);
  }

  return { success: m => show(m, 'success'), error: m => show(m, 'error', 5000),
           info: m => show(m, 'info'), warn: m => show(m, 'warn', 4500), show };
})();


/* ── HTTP helper ───────────────────────────────────────────────── */
async function apiFetch(url, opts = {}) {
  const defaults = {
    method:  opts.body ? 'POST' : 'GET',
    headers: { 'Content-Type': 'application/json' },
  };
  const merged = { ...defaults, ...opts,
    headers: { ...defaults.headers, ...(opts.headers || {}) } };
  if (merged.body && typeof merged.body !== 'string') {
    merged.body = JSON.stringify(merged.body);
  }
  const resp = await fetch(url, merged);
  const data = await resp.json().catch(() => ({ ok: false, error: 'Invalid JSON response' }));
  return data;
}


/* ── Key-Value Editor ──────────────────────────────────────────── */
class KVEditor {
  /**
   * @param {string} tbodyId  - id of the <tbody> element
   * @param {string} badgeId  - optional badge showing count
   */
  constructor(tbodyId, badgeId = null) {
    this.tbody  = document.getElementById(tbodyId);
    this.badge  = badgeId ? document.getElementById(badgeId) : null;
    if (!this.tbody) return;
    this._rows  = [];
    this._nextId = 0;
  }

  addRow(key = '', value = '', enabled = true) {
    if (!this.tbody) return;
    const id  = this._nextId++;
    const tr  = document.createElement('tr');
    tr.dataset.rowId = id;
    tr.innerHTML = `
      <td style="width:26px">
        <input type="checkbox" class="kv-check" ${enabled ? 'checked' : ''}
               onchange="this.closest('tr').dataset.disabled=!this.checked">
      </td>
      <td><input class="kv-key" placeholder="Key" value="${_esc(key)}" oninput="KVEditor._notify(this)"/></td>
      <td><input class="kv-val" placeholder="Value" value="${_esc(value)}" oninput="KVEditor._notify(this)"/></td>
      <td style="width:28px">
        <button class="kv-rm" onclick="this.closest('tr').remove();KVEditor._notifyParent(this)" title="Remove">✕</button>
      </td>`;
    this.tbody.appendChild(tr);
    this._updateBadge();
    return tr;
  }

  getDict() {
    if (!this.tbody) return {};
    const out = {};
    for (const tr of this.tbody.querySelectorAll('tr')) {
      const chk = tr.querySelector('.kv-check');
      if (chk && !chk.checked) continue;
      const k = tr.querySelector('.kv-key')?.value?.trim();
      const v = tr.querySelector('.kv-val')?.value;
      if (k) out[k] = v ?? '';
    }
    return out;
  }

  load(dict) {
    if (!this.tbody) return;
    this.tbody.innerHTML = '';
    this._nextId = 0;
    Object.entries(dict || {}).forEach(([k, v]) => this.addRow(k, String(v)));
    this._updateBadge();
  }

  clear() {
    if (this.tbody) this.tbody.innerHTML = '';
    this._updateBadge();
  }

  _updateBadge() {
    if (!this.badge || !this.tbody) return;
    const count = Object.keys(this.getDict()).length;
    this.badge.textContent = count;
    this.badge.style.display = count > 0 ? '' : 'none';
  }

  static _notify(input) {
    const tbody = input.closest('tbody');
    if (!tbody) return;
    // Re-count active keys for badge
    const id = tbody.closest('[data-kv-id]')?.dataset.kvId;
    if (id && window._kvEditors?.[id]) window._kvEditors[id]._updateBadge();
  }

  static _notifyParent(btn) {
    const tbody = btn.closest('tbody');
    if (!tbody) return;
    const id = tbody.closest('[data-kv-id]')?.dataset.kvId;
    if (id && window._kvEditors?.[id]) window._kvEditors[id]._updateBadge();
  }
}

function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


/* ── Poll run status ───────────────────────────────────────────── */
async function pollRunStatus(runId, onProgress, onDone, intervalMs = 1500) {
  async function tick() {
    try {
      const d = await apiFetch(`/api/run/${runId}/status`);
      if (!d.ok) { onDone(null, d.error || 'Status error'); return; }
      onProgress(d.run);
      if (d.run.status === 'done' || d.run.status === 'error') {
        onDone(d.run, null);
      } else {
        setTimeout(tick, intervalMs);
      }
    } catch (e) {
      onDone(null, e.message);
    }
  }
  setTimeout(tick, 500);
}


/* ── Download base64 file ──────────────────────────────────────── */
function downloadBase64(b64, filename, mimeType = 'application/octet-stream') {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const blob  = new Blob([bytes], { type: mimeType });
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}


/* ── Format helpers ────────────────────────────────────────────── */
function fmtMs(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function statusClass(code) {
  if (!code) return 's0';
  if (code >= 500) return 's5xx';
  if (code >= 400) return 's4xx';
  if (code >= 300) return 's3xx';
  return 's2xx';
}

function passRateColor(rate) {
  if (rate >= 90) return 'c-green';
  if (rate >= 60) return 'c-yellow';
  return 'c-red';
}

function badgeForRate(rate) {
  const cls = rate >= 80 ? 'bg-green' : rate >= 50 ? 'bg-yellow' : 'bg-red';
  return `<span class="badge ${cls}">${rate}%</span>`;
}

function methodBadge(m) {
  const map = { GET:'bg-blue',POST:'bg-green',PUT:'bg-yellow',PATCH:'bg-orange',DELETE:'bg-red',HEAD:'bg-gray',OPTIONS:'bg-gray' };
  return `<span class="badge ${map[m]||'bg-gray'} text-mono">${m}</span>`;
}

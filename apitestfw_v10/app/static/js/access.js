/**
 * access.js — Per-user page access control admin grid.
 * Checkbox matrix: Users × Pages. Save all at once or per-user.
 */
const AccessAdmin = (() => {
  let dirty = false;

  function init() {
    document.querySelectorAll('.access-chk').forEach(chk => {
      chk.addEventListener('change', () => { dirty = true; });
    });
    window.addEventListener('beforeunload', e => {
      if (dirty) e.returnValue = 'You have unsaved changes.';
    });
  }

  function _buildMatrix() {
    const matrix = {};
    document.querySelectorAll('.access-chk').forEach(chk => {
      const uid  = chk.dataset.uid;
      const page = chk.dataset.page;
      if (!matrix[uid]) matrix[uid] = {};
      matrix[uid][page] = chk.checked;
    });
    return matrix;
  }

  async function saveAll() {
    const matrix = _buildMatrix();
    const btn    = document.getElementById('save-all-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

    const data = await apiFetch('/api/access/save-all', { body: { matrix } });

    if (btn) { btn.disabled = false; btn.textContent = '💾 Save All Changes'; }

    if (data.ok) {
      dirty = false;
      Toast.success(`Saved ${data.total_updated} access rules ✓`);
    } else {
      Toast.error(data.errors?.join(', ') || 'Save failed');
    }
  }

  async function resetUser(uid, role) {
    if (!confirm(`Reset this user's access to ${role} role defaults?`)) return;
    const data = await apiFetch(`/api/access/user/${uid}/reset`, { body: {} });
    if (data.ok) {
      Toast.success(`Reset to ${data.role} defaults`);
      setTimeout(() => location.reload(), 800);
    } else {
      Toast.error(data.error || 'Reset failed');
    }
  }

  function selectAll(uid) {
    document.querySelectorAll(`.access-chk[data-uid="${uid}"]`)
      .forEach(c => { c.checked = true; dirty = true; });
  }

  function selectNone(uid) {
    document.querySelectorAll(`.access-chk[data-uid="${uid}"]`)
      .forEach(c => { c.checked = false; dirty = true; });
  }

  function togglePage(page, allChecked) {
    document.querySelectorAll(`.access-chk[data-page="${page}"]`)
      .forEach(c => { c.checked = allChecked; dirty = true; });
  }

  return { init, saveAll, resetUser, selectAll, selectNone, togglePage };
})();

document.addEventListener('DOMContentLoaded', () => AccessAdmin.init());

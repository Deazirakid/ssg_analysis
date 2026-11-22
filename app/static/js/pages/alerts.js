(() => {
  const $ = id => document.getElementById(id);
  const describe = p => Object.entries(p).filter(([k]) => k !== 'region' || p[k] !== 'tbilisi').map(([k, v]) => `${k}=${v}`).join(' · ') || 'Tbilisi, all';
  async function load() {
    const [ss, al] = await Promise.all([App.api('/api/alerts/searches'), App.api('/api/alerts', { limit: 300 })]);
    App.table($('t-ss'), [
      { key: 'name', label: 'Name', render: (v, r) => `<a href="/listings?${new URLSearchParams(r.params)}">${App.esc(v)}</a>` },
      { key: 'params', label: 'Filters', render: v => `<span style="color:var(--ink-3)">${App.esc(describe(v))}</span>` },
      { key: 'matches', label: 'Matches now', num: true, render: App.fmt },
      { key: 'notify_new', label: 'New', render: v => v ? '<span class="badge good">on</span>' : '<span class="badge">off</span>' },
      { key: 'notify_drops', label: 'Drops', render: v => v ? '<span class="badge good">on</span>' : '<span class="badge">off</span>' },
      { key: 'telegram', label: 'Telegram', render: v => v ? '<span class="badge blue">on</span>' : '–' },
      { key: 'last_run', label: 'Last evaluated' },
      { key: 'id', label: '', render: v => `<button class="btn ghost danger" data-del="${v}"><i data-lucide="trash-2"></i></button>` }], ss);
    $('t-ss').querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { await App.send('DELETE', '/api/alerts/searches/' + b.dataset.del); load(); });
    App.table($('t-al'), [
      { key: 'created_at', label: 'When' }, { key: 'kind', label: 'Type', render: v => v === 'drop' ? '<span class="badge good">Price drop</span>' : '<span class="badge blue">New</span>' },
      { key: 'title', label: 'Listing', render: (v, r) => `<a href="${App.esc(r.url)}" target="_blank" rel="noopener">${App.esc(v)}</a>` },
      { key: 'detail', label: 'Detail' }, { key: 'search_name', label: 'Search' },
      { key: 'is_read', label: '', render: v => v ? '' : '<span class="badge warn">unread</span>' }], al.rows);
    App.icons();
  }
  $('al-read').onclick = async () => { await App.post('/api/alerts/read'); load(); };
  $('al-eval').onclick = async () => { const r = await App.post('/api/alerts/evaluate'); App.toast(r.message || `${r.created} alerts created for run ${r.run}`); load(); };
  App.api('/api/options').then(o => { $('snap').textContent = `Snapshot ${o.snapshot} · ${App.fmt(o.total)} clean listings`; });
  load();
})();

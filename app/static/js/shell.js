// App shell: icons, theme toggle, Ctrl+K command palette, alerts bell.
(() => {
  const $ = id => document.getElementById(id);
  const icons = () => window.lucide && lucide.createIcons({ attrs: { 'stroke-width': 1.9 } });
  icons();
  App.icons = icons;

  // ----- theme -----
  const isDark = () => document.documentElement.dataset.theme === 'dark' ||
    (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
  $('theme').onclick = () => {
    const t = isDark() ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('ssge.theme', t); } catch {}
    window.dispatchEvent(new CustomEvent('theme:change', { detail: t }));
    if (document.querySelector('canvas, #map')) location.reload();
  };
  App.isDark = isDark;

  // ----- modal helper -----
  App.modal = (html, onMount) => {
    $('modal-body').innerHTML = html; $('modal').classList.add('open'); icons();
    const close = () => $('modal').classList.remove('open');
    $('modal').onclick = e => { if (e.target.id === 'modal') close(); };
    $('modal-body').querySelectorAll('[data-close]').forEach(b => b.onclick = close);
    onMount && onMount($('modal-body'), close);
    return close;
  };

  // ----- command palette -----
  const pages = Object.values(window.NAV || {}).flat().map(([k, v]) => ({ key: k, href: v[0], title: v[1], icon: v[2], group: v[3] }));
  if (document.body.dataset.role === 'admin') pages.push({ href: '/docs', title: 'API docs (Swagger)', icon: 'braces', group: 'Admin' });
  let sel = 0, items = [];
  function renderPalette() {
    const q = $('palette-q').value.trim().toLowerCase();
    items = pages.filter(p => !q || p.title.toLowerCase().includes(q) || p.group.toLowerCase().includes(q));
    const isId = /^\d{5,10}$/.test(q);
    let html = '';
    if (isId) html += `<div class="sec">Listing</div><div class="it" data-href="/listings?q=${q}&region=all"><i data-lucide="hash"></i>Open listing ${q}<small>Listings</small></div>`;
    html += '<div class="sec">Pages</div>' + items.map((p, i) => `<div class="it" data-href="${p.href}"><i data-lucide="${p.icon}"></i>${App.esc(p.title)}<small>${App.esc(p.group)}</small></div>`).join('');
    $('palette-items').innerHTML = html; icons();
    const all = [...$('palette-items').querySelectorAll('.it')];
    sel = Math.min(sel, all.length - 1); all.forEach((el, i) => el.classList.toggle('sel', i === sel));
    all.forEach(el => el.onclick = () => go(el.dataset.href));
  }
  const go = href => { const keep = href.startsWith('/docs') || href.includes('?') ? '' : location.search; location.href = href + keep; };
  const openP = () => { $('palette').classList.add('open'); $('palette-q').value = ''; sel = 0; renderPalette(); setTimeout(() => $('palette-q').focus(), 10); };
  const closeP = () => $('palette').classList.remove('open');
  $('open-palette').onclick = openP;
  $('palette').onclick = e => { if (e.target.id === 'palette') closeP(); };
  $('palette-q').oninput = () => { sel = 0; renderPalette(); };
  $('palette-q').onkeydown = e => {
    const all = [...$('palette-items').querySelectorAll('.it')];
    if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, all.length - 1); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); e.preventDefault(); }
    else if (e.key === 'Enter' && all[sel]) { go(all[sel].dataset.href); return; }
    else if (e.key === 'Escape') { closeP(); return; } else return;
    all.forEach((el, i) => el.classList.toggle('sel', i === sel));
  };
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); openP(); }
    if (e.key === 'Escape') { closeP(); $('modal').classList.remove('open'); $('bell-drop').classList.remove('open'); }
  });

  // ----- alerts bell -----
  async function bell() {
    try {
      const a = await App.api('/api/alerts', { limit: 12 });
      const dot = $('bell-dot'), nav = $('nav-alerts');
      dot.hidden = !a.unread; dot.textContent = a.unread > 99 ? '99+' : a.unread;
      if (nav) { nav.hidden = !a.unread; nav.textContent = a.unread; }
      $('bell-list').innerHTML = a.rows.length ? a.rows.map(r => `<a class="al ${r.is_read ? '' : 'unread'}" href="${App.esc(r.url)}" target="_blank" rel="noopener">
        <span class="badge ${r.kind === 'drop' ? 'good' : 'blue'}">${r.kind === 'drop' ? 'Price drop' : 'New'}</span> ${App.esc(r.title)}
        <small>${App.esc(r.detail)} · ${App.esc(r.search_name || '')}</small></a>`).join('') : '<div class="empty">No alerts yet. Save a search to get notified.</div>';
    } catch {}
  }
  $('bell').onclick = e => { e.stopPropagation(); $('bell-drop').classList.toggle('open'); };
  $('bell-drop').onclick = e => e.stopPropagation();
  document.addEventListener('click', () => $('bell-drop').classList.remove('open'));
  $('bell-read').onclick = async () => { await App.post('/api/alerts/read'); bell(); };
  bell(); setInterval(bell, 120000);
})();

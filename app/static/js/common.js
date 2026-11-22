// Shared helpers: API calls, formatting, toast.
const App = (() => {
  const nf = new Intl.NumberFormat('en-US');
  const fmt = (v, d = 0) => { d = Number.isInteger(d) && d >= 0 && d <= 6 ? d : 0; return (v == null || Number.isNaN(+v)) ? '–' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d }); };
  const usd = v => v == null ? '–' : (v < 0 ? '−$' + fmt(-v) : '$' + fmt(v));
  const compact = v => v == null ? '–' : v < 0 ? '−' + compact(-v) : (Math.abs(v) >= 1e6 ? '$' + (v / 1e6).toFixed(2) + 'M' : Math.abs(v) >= 1e4 ? '$' + Math.round(v / 1e3) + 'k' : '$' + nf.format(Math.round(v)));
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function api(path, params) {
    const qs = params ? (params instanceof URLSearchParams ? params : new URLSearchParams(params)).toString() : '';
    const url = path + (qs ? (path.includes('?') ? '&' : '?') + qs : '');
    for (let attempt = 0; attempt < 6; attempt++) {
      const r = await fetch(url, { credentials: 'same-origin' });
      if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search); throw new Error('auth'); }
      if (r.status === 503) { toast('Data is loading from the database…'); await new Promise(res => setTimeout(res, 2500)); continue; }
      if (!r.ok) { toast('Request failed: ' + r.status); throw new Error(r.status); }
      return r.json();
    }
    throw new Error('timeout');
  }
  async function send(method, path, body) {
    const r = await fetch(path, { method, credentials: 'same-origin',
      headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
    if (r.status === 401) { location.href = '/login'; throw new Error('auth'); }
    const data = await r.json().catch(() => ({}));
    if (!r.ok) { const msg = typeof data.detail === 'string' ? data.detail : (data.detail?.[0]?.msg || r.status); toast('Error: ' + msg); throw new Error(msg); }
    return data;
  }
  const post = (path, body) => send('POST', path, body);
  let tt;
  function toast(msg, ms = 2600) {
    const el = document.getElementById('toast'); if (!el) return;
    el.textContent = msg; el.style.display = 'block'; clearTimeout(tt);
    tt = setTimeout(() => el.style.display = 'none', ms);
  }
  function table(el, cols, rows, opts = {}) {
    if (!rows.length) { el.innerHTML = `<tbody><tr><td class="empty">No data for these filters</td></tr></tbody>`; return; }
    const maxOf = {}; cols.filter(c => c.bar).forEach(c => maxOf[c.key] = Math.max(...rows.map(r => +r[c.key] || 0)));
    const th = cols.map(c => `<th class="${c.num ? 'num' : ''} ${c.sort ? 'sort' : ''}" data-key="${c.key}">${esc(c.label)}${opts.sort === c.key ? (opts.dir === 'asc' ? ' ▲' : ' ▼') : ''}</th>`).join('');
    const tb = rows.map(r => '<tr>' + cols.map(c => {
      const raw = r[c.key], txt = c.render ? c.render(raw, r) : esc(raw ?? '–');
      if (c.bar) { const w = maxOf[c.key] ? Math.max(2, 100 * (+raw || 0) / maxOf[c.key]) : 0; return `<td class="num bar-cell"><span class="b" style="width:${w}%"></span><span class="t">${txt}</span></td>`; }
      return `<td class="${c.num ? 'num' : ''}" title="${c.num ? '' : esc(raw ?? '')}">${txt}</td>`;
    }).join('') + '</tr>').join('');
    el.innerHTML = `<thead><tr>${th}</tr></thead><tbody>${tb}</tbody>`;
    if (opts.onSort) el.querySelectorAll('th.sort').forEach(h => h.onclick = () => opts.onSort(h.dataset.key));
  }
  return { fmt, usd, compact, esc, api, post, send, toast, table, pct: v => v == null ? '–' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%' };
})();

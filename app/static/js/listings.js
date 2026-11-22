(() => {
  let page = 1, size = 50, sort = 'created', dir = 'desc', params = null, total = 0;
  const $ = id => document.getElementById(id);
  const cols = [
    { key: 'id', label: 'ID', sort: true, render: (v, r) => `<a href="${App.esc(r.url)}" target="_blank" rel="noopener">${v}</a>` },
    { key: 'title', label: 'Title' },
    { key: 'subdistrict', label: 'Neighbourhood', sort: true, render: (v, r) => App.esc(v || r.city || '–') },
    { key: 'street', label: 'Street' },
    { key: 'price_usd', label: 'Price', num: true, sort: true, render: v => App.usd(v) },
    { key: 'usd_per_m2', label: '$/m²', num: true, sort: true, render: v => App.usd(v) },
    { key: 'area_m2', label: 'm²', num: true, sort: true, render: v => App.fmt(v) },
    { key: 'rooms', label: 'Rooms', num: true, sort: true, render: v => v ?? '–' },
    { key: 'floor', label: 'Floor', num: true, sort: true, render: (v, r) => v == null ? '–' : `${v}/${r.floors_total ?? '?'}` },
    { key: 'is_project', label: 'Segment', render: v => v ? '<span class="badge new">New build</span>' : '<span class="badge">Resale</span>' },
    { key: 'near_subway', label: 'Metro' },
    { key: 'created', label: 'Listed', sort: true },
    { key: 'id', label: '', render: v => `<a href="/invest?id=${v}" title="Investment calculator"><i data-lucide="calculator"></i></a>` },
  ];
  async function load() {
    const q = new URLSearchParams(params); q.set('page', page); q.set('size', size); q.set('sort', sort); q.set('dir', dir);
    $('t-list').classList.add('loading');
    const d = await App.api('/api/listings', q);
    total = d.total;
    App.table($('t-list'), cols, d.rows, { sort, dir, onSort: k => { dir = sort === k && dir === 'desc' ? 'asc' : 'desc'; sort = k; page = 1; load(); } });
    $('t-list').classList.remove('loading');
    const pages = Math.max(1, Math.ceil(total / size));
    $('l-count').textContent = `${App.fmt(total)} listings`;
    $('l-page').textContent = `Page ${page} of ${App.fmt(pages)}`;
    $('l-prev').disabled = page <= 1; $('l-next').disabled = page >= pages;
    $('l-export').href = '/api/listings.csv?' + new URLSearchParams(params).toString();
    $('l-xlsx').href = '/api/export/listings.xlsx?' + new URLSearchParams(params).toString();
    App.icons();
  }
  $('l-sheets').onclick = () => {
    const isAdmin = document.body.dataset.role === 'admin';
    const url = `${location.origin}/api/export/sheets.csv?api_key=YOUR_KEY&${new URLSearchParams(params).toString()}`;
    App.modal(`<h3>Live Google Sheets feed</h3>
      <p style="margin:0;color:var(--ink-2);font-size:13px">Paste this formula into cell A1 of a Google Sheet. It refreshes about every hour and keeps the current filters. The server must be reachable from the internet (deploy on Renode). Replace <b>YOUR_KEY</b> with an API key${isAdmin ? ' from <a href="/users">Users & API keys</a>' : ' from your admin'}.</p>
      <div class="code" id="sh-f">=IMPORTDATA("${App.esc(url)}")</div>
      <p style="margin:0;color:var(--ink-3);font-size:12.5px">One-off instead? Download the Excel file and use File → Import in Google Sheets.</p>
      <div class="acts"><button class="btn" data-close>Close</button><button class="btn primary" id="sh-copy"><i data-lucide="copy"></i>Copy formula</button></div>`,
      el => el.querySelector('#sh-copy').onclick = () => { navigator.clipboard.writeText(el.querySelector('#sh-f').textContent); App.toast('Copied'); });
  };
  $('l-prev').onclick = () => { page--; load(); };
  $('l-next').onclick = () => { page++; load(); };
  $('l-size').onchange = e => { size = +e.target.value; page = 1; load(); };
  Filters.onChange(p => { params = p; page = 1; load(); });
  Filters.init();
})();

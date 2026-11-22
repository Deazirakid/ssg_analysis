(() => {
  const $ = id => document.getElementById(id);
  let disc = 15, dir = 'down', params = null;
  const link = (v, r) => `<a href="${App.esc(r.url)}" target="_blank" rel="noopener">${v}</a>`;
  const calc = v => `<a href="/invest?id=${v}" title="Investment calculator"><i data-lucide="calculator"></i></a>`;

  async function loadDeals() {
    const rows = await App.api('/api/market/deals', new URLSearchParams([...params, ['min_discount', disc]]));
    App.table($('t-deals'), [
      { key: 'id', label: 'ID', render: link }, { key: 'title', label: 'Title' }, { key: 'subdistrict', label: 'Neighbourhood' },
      { key: 'price_usd', label: 'Price', num: true, render: App.usd }, { key: 'usd_per_m2', label: '$/m²', num: true, render: App.usd },
      { key: 'bench_m2', label: 'Area median $/m²', num: true, render: App.usd },
      { key: 'discount_pct', label: 'Discount', num: true, bar: true, render: v => `<span class="pos">−${v}%</span>` },
      { key: 'saving_usd', label: 'Saving vs median', num: true, render: v => App.compact(v) },
      { key: 'area_m2', label: 'm²', num: true, render: App.fmt }, { key: 'rooms', label: 'Rooms', num: true },
      { key: 'bench_n', label: 'Comparables', num: true }, { key: 'id', label: '', render: calc }], rows);
    $('d-kpis').innerHTML = [
      ['badge-percent', 'Deals found', App.fmt(rows.length), `${disc}–60% below area median (top 100) · deeper = see Fraud & quality`],
      ['piggy-bank', 'Median discount', rows.length ? rows[Math.floor(rows.length / 2)].discount_pct + '%' : '–', 'among listed deals'],
      ['coins', 'Biggest saving', rows.length ? App.compact(Math.max(...rows.map(r => r.saving_usd || 0))) : '–', 'vs neighbourhood median'],
    ].map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('') + $('d-kpis').dataset.drops;
    App.icons();
  }
  async function loadDrops() {
    const d = await App.api('/api/market/drops', new URLSearchParams([...params, ['direction', dir]]));
    if (!d.summary) {
      $('drop-hint').textContent = d.message;
      $('t-drops').innerHTML = `<tbody><tr><td class="empty">${App.esc(d.message)}</td></tr></tbody>`;
      $('d-kpis').dataset.drops = ''; return;
    }
    $('drop-hint').textContent = `Run ${d.runs[0]} → ${d.runs[1]} · ${App.fmt(d.summary.changed)} listings changed price`;
    $('d-kpis').dataset.drops = `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="trending-down"></i></span>Price drops</div><div class="value">${App.fmt(d.summary.drops)}</div><div class="sub">median ${d.summary.median_drop_pct ?? '–'}% · ${App.fmt(d.summary.rises)} rises</div></div>`;
    App.table($('t-drops'), [
      { key: 'id', label: 'ID', render: link }, { key: 'title', label: 'Title' }, { key: 'subdistrict', label: 'Neighbourhood' },
      { key: 'old_price', label: 'Was', num: true, render: App.usd }, { key: 'price_usd', label: 'Now', num: true, render: App.usd },
      { key: 'change_pct', label: 'Change', num: true, render: v => `<span class="${v < 0 ? 'pos' : 'neg'}">${App.pct(v)}</span>` },
      { key: 'change_usd', label: 'USD', num: true, render: v => App.compact(v) }, { key: 'usd_per_m2', label: '$/m² now', num: true, render: App.usd },
      { key: 'area_m2', label: 'm²', num: true, render: App.fmt }, { key: 'id', label: '', render: calc }], d.rows);
  }
  async function load(p) {
    params = p || params;
    document.querySelector('.content').classList.add('loading');
    try { await loadDrops(); await loadDeals(); } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  const seg = (id, fn) => $(id).querySelectorAll('button').forEach(b => b.onclick = () => { $(id).querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); fn(b.dataset.v); });
  seg('disc', v => { disc = +v; load(); });
  seg('dir', v => { dir = v; load(); });
  $('d-kpis').dataset.drops = '';
  Filters.onChange(load); Filters.init();
})();

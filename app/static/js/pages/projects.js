(() => {
  const $ = id => document.getElementById(id);
  async function load(p) {
    $('t-proj').classList.add('loading');
    const rows = await App.api('/api/market/projects', p);
    $('t-proj').classList.remove('loading');
    App.table($('t-proj'), [
      { key: 'street', label: 'Building', render: (v, r) => `<a href="${App.esc(r.sample_url)}" target="_blank" rel="noopener">${App.esc(v || 'Unnamed street')}</a>` },
      { key: 'subdistrict', label: 'Neighbourhood' },
      { key: 'new_build_pct', label: 'New build', num: true, render: v => v >= 50 ? `<span class="badge good">${v}%</span>` : v + '%' },
      { key: 'floors', label: 'Floors', num: true, render: v => v ?? '–' },
      { key: 'units', label: 'Units listed', num: true, bar: true, render: App.fmt },
      { key: 'median_m2', label: 'Median $/m²', num: true, render: App.usd },
      { key: 'resale_m2', label: 'Resale $/m² nearby', num: true, render: App.usd },
      { key: 'premium_pct', label: 'vs resale', num: true, render: v => v == null ? '–' : `<span class="${v > 0 ? 'neg' : 'pos'}">${App.pct(v)}</span>` },
      { key: 'min_price', label: 'From', num: true, render: App.compact }, { key: 'max_price', label: 'To', num: true, render: App.compact },
      { key: 'median_area', label: 'Median m²', num: true, render: App.fmt }, { key: 'sellers', label: 'Sellers', num: true },
      { key: 'lat', label: 'Map', render: (v, r) => v ? `<a href="https://www.google.com/maps?q=${r.lat},${r.lon}" target="_blank" rel="noopener"><i data-lucide="map-pin"></i></a>` : '' }], rows);
    const prem = rows.filter(r => r.premium_pct != null).map(r => r.premium_pct).sort((a, b) => a - b);
    $('p-kpis').innerHTML = [
      ['building-2', 'Buildings', App.fmt(rows.length), `4+ units on one pin · ${rows.filter(r => r.new_build_pct >= 50).length} mostly new-build`],
      ['layers', 'Units listed', App.fmt(rows.reduce((a, r) => a + r.units, 0)), 'across these buildings'],
      ['scale', 'Median premium vs resale', prem.length ? App.pct(prem[Math.floor(prem.length / 2)]) : '–', 'same neighbourhood, USD/m²'],
    ].map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('');
    App.icons();
  }
  Filters.onChange(load); Filters.init();
})();

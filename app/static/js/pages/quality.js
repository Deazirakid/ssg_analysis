(() => {
  const $ = id => document.getElementById(id);
  const link = (v, r) => `<a href="${App.esc(r.url)}" target="_blank" rel="noopener">${v}</a>`;
  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const d = await App.api('/api/market/fraud', p);
      $('q-kpis').innerHTML = [
        ['alert-triangle', 'Suspiciously low', App.fmt(d.summary.low_price), '< 50% of area median (top 100 shown)'],
        ['copy', 'Duplicate clusters', App.fmt(d.summary.dup_clusters.n), `${App.fmt(d.summary.dup_clusters.listings)} listings involved (all feed rows)`],
        ['users', 'Heavy posters', App.fmt(d.summary.heavy_posters), 'posters with 50+ active listings'],
        ['type', 'Template titles', App.fmt(d.same_title.length), 'same title in 4+ neighbourhoods'],
      ].map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('');
      App.table($('t-low'), [{ key: 'id', label: 'ID', render: link }, { key: 'title', label: 'Title' }, { key: 'subdistrict', label: 'Neighbourhood' },
        { key: 'price_usd', label: 'Price', num: true, render: App.usd }, { key: 'usd_per_m2', label: '$/m²', num: true, render: App.usd },
        { key: 'bench_m2', label: 'Area median', num: true, render: App.usd }, { key: 'discount_pct', label: 'Below', num: true, bar: true, render: v => `<span class="neg">−${v}%</span>` },
        { key: 'area_m2', label: 'm²', num: true, render: App.fmt }, { key: 'poster_n', label: 'Poster listings', num: true, render: v => v ?? '–' }], d.low_price);
      App.table($('t-dup'), [{ key: 'title', label: 'Title' }, { key: 'subdistrict', label: 'Neighbourhood' }, { key: 'street', label: 'Street' },
        { key: 'price_usd', label: 'Price', num: true, render: App.usd }, { key: 'area_m2', label: 'm²', num: true, render: App.fmt },
        { key: 'n', label: 'Copies', num: true, bar: true }, { key: 'posters', label: 'Posters', num: true, render: v => v > 1 ? `<span class="badge warn">${v}</span>` : v },
        { key: 'ids', label: 'IDs', render: v => (v || '').split(',').slice(0, 4).map(i => `<a href="https://home.ss.ge/ka/udzravi-qoneba/x-${i}" target="_blank" rel="noopener">${i}</a>`).join(' ') }], d.duplicates);
      App.table($('t-title'), [{ key: 'title', label: 'Title' }, { key: 'n', label: 'Listings', num: true, bar: true }, { key: 'areas', label: 'Areas', num: true },
        { key: 'prices', label: 'Distinct prices', num: true }, { key: 'min_price', label: 'Min', num: true, render: App.compact }, { key: 'max_price', label: 'Max', num: true, render: App.compact }], d.same_title);
      App.icons();
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load); Filters.init();
})();

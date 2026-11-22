(() => {
  const $ = id => document.getElementById(id);
  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const d = await App.api('/api/market/distance', p);
      const m = d.metro.filter(r => r.n >= 10);
      C.line('c-metro', m.map(r => (r.km >= 3 ? '3+' : r.km.toFixed(2)) + ' km'), m.map(r => r.m2), { fmtv: App.usd, label: 'Median USD/m²' });
      const c = d.center.filter(r => r.n >= 10);
      C.line('c-center', c.map(r => (r.km >= 15 ? '15+' : r.km) + ' km'), c.map(r => r.m2), { fmtv: App.usd, label: 'Median USD/m²', color: C.S.s2 });
      C.hbar('c-stations', d.stations.map(s => s.name), d.stations.map(s => s.m2), { fmtv: App.usd, label: 'Median USD/m²' });
      App.table($('t-stations'), [{ key: 'name', label: 'Station' }, { key: 'm2', label: 'Median $/m²', num: true, bar: true, render: App.usd },
        { key: 'n', label: 'Listings ≤800 m', num: true, render: App.fmt }, { key: 'km', label: 'Median dist.', num: true, render: v => v + ' km' }], d.stations);
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load); Filters.init();
})();

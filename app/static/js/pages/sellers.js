(() => {
  const $ = id => document.getElementById(id);
  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const d = await App.api('/api/market/sellers', p);
      const total = d.split.reduce((a, s) => a + s.n, 0);
      const get = k => d.split.find(s => s.seller === k) || {};
      const b = get('Broker / agency'), o = get('Private owner');
      $('s-kpis').innerHTML = [
        ['briefcase', 'Broker / agency share', total ? (100 * (b.n || 0) / total).toFixed(1) + '%' : '–', `${App.fmt(b.n)} listings`],
        ['user', 'Private owners', total ? (100 * (o.n || 0) / total).toFixed(1) + '%' : '–', `${App.fmt(o.n)} listings`],
        ['ruler', 'Broker median $/m²', App.usd(b.median_m2), `owner ${App.usd(o.median_m2)}`],
        ['percent', 'Broker price gap', b.median_m2 && o.median_m2 ? App.pct((b.median_m2 / o.median_m2 - 1) * 100) : '–', 'broker vs owner, USD/m²'],
      ].map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('');
      const top = d.by_area.slice(0, 25);
      C.hbar('c-broker', top.map(r => r.name), top.map(r => r.broker_pct), { fmtv: v => v.toFixed(0) + '%', label: 'Broker share', color: C.S.s6 });
      App.table($('t-posters'), [{ key: 'poster', label: 'Poster', render: v => `<code>${v}</code>` }, { key: 'n', label: 'Listings', num: true, bar: true, render: App.fmt },
        { key: 'areas', label: 'Areas', num: true }, { key: 'median_m2', label: '$/m²', num: true, render: App.usd }, { key: 'types', label: 'Types' }], d.top_posters);
      App.table($('t-sell-area'), [{ key: 'name', label: 'Neighbourhood' }, { key: 'n', label: 'Listings', num: true, render: App.fmt },
        { key: 'broker_pct', label: 'Broker share', num: true, bar: true, render: v => v + '%' }, { key: 'broker_m2', label: 'Broker $/m²', num: true, render: App.usd },
        { key: 'owner_m2', label: 'Owner $/m²', num: true, render: App.usd },
        { key: 'broker_m2', label: 'Gap', num: true, render: (v, r) => v && r.owner_m2 ? App.pct((v / r.owner_m2 - 1) * 100) : '–' }], d.by_area);
      App.icons();
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load); Filters.init();
})();

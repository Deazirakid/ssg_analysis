(() => {
  const usdm2 = v => App.usd(v);
  const cnt = v => App.fmt(v);

  function kpis(k) {
    const d = k.prev_7d ? (k.new_7d - k.prev_7d) / k.prev_7d * 100 : null;
    const tiles = [
      ['home', 'Listings', App.fmt(k.listings), 'matching filters'],
      ['wallet', 'Median price', App.compact(k.median_price), `median area ${App.fmt(k.median_area)} m²`],
      ['ruler', 'Median USD / m²', App.usd(k.median_m2), `IQR ${App.usd(k.p25_m2)} – ${App.usd(k.p75_m2)}`],
      ['sparkles', 'New in last 7 days', App.fmt(k.new_7d), d == null ? 'vs previous week: –' : `<span class="delta ${d >= 0 ? 'up' : 'down'}">${d >= 0 ? '↑' : '↓'} ${Math.abs(d).toFixed(0)}%</span> vs previous week`],
      ['building-2', 'New build share', (k.new_build_pct ?? 0) + '%', 'listings linked to a project'],
      ['move-horizontal', 'Price spread', k.p25_m2 ? (k.p75_m2 / k.p25_m2).toFixed(2) + '×' : '–', 'p75 ÷ p25 USD/m²'],
    ];
    document.getElementById('kpis').innerHTML = tiles.map(([ic, l, v, s]) =>
      `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${ic}"></i></span>${l}</div><div class="value">${v}</div><div class="sub">${s}</div></div>`).join('');
    App.icons();
  }

  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const [k, hoods, daily, hist, rooms, mix] = await Promise.all([
        App.api('/api/overview/kpis', p), App.api('/api/overview/neighbourhoods', p), App.api('/api/overview/daily', p),
        App.api('/api/overview/histogram', p), App.api('/api/overview/rooms', p), App.api('/api/overview/mix', p)]);
      kpis(k);
      const byM2 = [...hoods].sort((a, b) => b.median_m2 - a.median_m2);
      C.hbar('c-hood-m2', byM2.map(h => h.name), byM2.map(h => h.median_m2), { fmtv: usdm2, label: 'Median USD/m²' });
      C.hbar('c-hood-n', hoods.map(h => h.name), hoods.map(h => h.n), { fmtv: cnt, label: 'Listings', color: C.S.s3 });
      C.line('c-daily', daily.map(d => d.d.slice(5)), daily.map(d => d.n), { fmtv: cnt, label: 'New listings' });
      C.line('c-daily-m2', daily.map(d => d.d.slice(5)), daily.map(d => d.m2), { fmtv: usdm2, label: 'Median USD/m²', color: C.S.s2 });
      C.vbar('c-hist', hist.bins.map(b => App.fmt(b.from)), hist.bins.map(b => b.n), { fmtv: cnt, label: 'Listings' });
      C.vbar('c-rooms', rooms.map(r => r.r + (r.r === '1' ? ' room' : ' rooms')), rooms.map(r => r.median_m2), { fmtv: usdm2, label: 'Median USD/m²' });
      const byType = {}; mix.forEach(m => byType[m.type] = (byType[m.type] || 0) + m.n);
      const types = Object.entries(byType).sort((a, b) => b[1] - a[1]);
      C.hbar('c-mix', types.map(t => t[0]), types.map(t => t[1]), { fmtv: cnt, label: 'Listings' });
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load);
  Filters.init();
})();

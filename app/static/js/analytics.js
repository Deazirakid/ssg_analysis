(() => {
  const usd = v => App.usd(v), cnt = v => App.fmt(v);

  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const [yld, dist, sc, fl, seg, st] = await Promise.all([
        App.api('/api/analytics/yield', p), App.api('/api/analytics/districts', p), App.api('/api/analytics/scatter', p),
        App.api('/api/analytics/floors', p), App.api('/api/analytics/segments', p), App.api('/api/analytics/streets', p)]);

      const top = yld.slice(0, 25);
      C.hbar('c-yield', top.map(r => r.name), top.map(r => r.yield_pct), { fmtv: v => v.toFixed(1) + '%', label: 'Gross yield', color: C.S.s3 });
      App.table(document.getElementById('t-yield'), [
        { key: 'name', label: 'Neighbourhood' }, { key: 'yield_pct', label: 'Yield', num: true, bar: true, render: v => v.toFixed(2) + '%' },
        { key: 'payback_years', label: 'Payback', num: true, render: v => v == null ? '–' : v + ' y' },
        { key: 'sale_m2', label: 'Sale $/m²', num: true, render: usd }, { key: 'rent', label: 'Rent /mo', num: true, render: usd },
        { key: 'n_sale', label: '# sale', num: true, render: cnt }, { key: 'n_rent', label: '# rent', num: true, render: cnt }], yld);

      C.draw('c-dist', { type: 'bar', data: { labels: dist.map(d => d.name), datasets: [
          { label: 'IQR', data: dist.map(d => [d.p25, d.p75]), backgroundColor: C.S.s1 + '40', borderRadius: 4, borderSkipped: false, barPercentage: .7 },
          { type: 'scatter', label: 'Median', data: dist.map((d, i) => ({ x: d.name, y: d.median_m2 })), backgroundColor: C.S.s1, pointRadius: 5, pointStyle: 'rectRot' }] },
        options: { plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: c => c.dataset.label === 'IQR' ? ` p25–p75: ${usd(c.raw[0])} – ${usd(c.raw[1])}` : ` median: ${usd(c.parsed.y)}` } } },
          scales: { x: { grid: C.nogrid, ticks: { maxRotation: 30, autoSkip: false, font: { size: 10.5 } } }, y: { grid: C.grid, beginAtZero: true, ticks: { callback: usd } } } } });

      C.draw('c-scatter', { type: 'scatter', data: { datasets: [{ data: sc.map(r => ({ x: r.x, y: r.y, s: r.subdistrict, m: r.m2 })), backgroundColor: C.S.s1 + '55', borderColor: C.S.s1, borderWidth: .5, pointRadius: 2.5, pointHoverRadius: 6 }] },
        options: { scales: { x: { type: 'logarithmic', grid: C.grid, title: { display: true, text: 'Area m² (log)' }, ticks: { callback: v => [10, 20, 50, 100, 200, 500, 1000, 2000, 5000].includes(v) ? v : '' } },
                             y: { type: 'logarithmic', grid: C.grid, title: { display: true, text: 'Price USD (log)' }, ticks: { callback: v => [1e3, 1e4, 3e4, 1e5, 3e5, 1e6, 3e6].includes(v) ? App.compact(v) : '' } } },
          plugins: { tooltip: { callbacks: { label: c => ` ${App.compact(c.raw.y)} · ${c.raw.x} m² · ${usd(c.raw.m)}/m² · ${c.raw.s || ''}` } } } } });

      C.vbar('c-floor', fl.map(f => f.bucket), fl.map(f => f.median_m2), { fmtv: usd, label: 'Median USD/m²' });
      C.vbar('c-build', seg.build.map(s => `${s.k} (${cnt(s.n)})`), seg.build.map(s => s.median_m2), { fmtv: usd, label: 'Median USD/m²' });
      const am = [...seg.furniture, ...seg.metro];
      C.vbar('c-amen', am.map(s => s.k), am.map(s => s.median_m2), { fmtv: usd, label: 'Median USD/m²', color: C.S.s2 });

      App.table(document.getElementById('t-streets'), [
        { key: 'street', label: 'Street' }, { key: 'subdistrict', label: 'Neighbourhood' },
        { key: 'median_m2', label: 'Median $/m²', num: true, bar: true, render: usd },
        { key: 'median_price', label: 'Median price', num: true, render: v => App.compact(v) }, { key: 'n', label: 'Listings', num: true, render: cnt }], st);
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load);
  Filters.init();
})();

(() => {
  const $ = id => document.getElementById(id);
  const SER = () => [C.S.s1, C.S.s2, C.S.s3, C.S.s4, C.S.s5, C.S.s6];
  async function load(p) {
    document.querySelector('.content').classList.add('loading');
    try {
      const [t, hoods, dom] = await Promise.all([App.api('/api/market/trends', p),
        App.api('/api/market/trends', new URLSearchParams([...p, ['by', 'subdistrict']])), App.api('/api/market/dom', p)]);
      const w = t.weekly;
      C.line('c-week', w.map(r => r.wk.slice(5)), w.map(r => r.m2), { fmtv: App.usd, label: 'Median USD/m²' });
      C.vbar('c-week-n', w.map(r => r.wk.slice(5)), w.map(r => r.n), { fmtv: App.fmt, label: 'New listings' });
      const weeks = [...new Set(Object.values(hoods.series).flat().map(r => r.wk))].sort();
      C.draw('c-hoods', { type: 'line', data: { labels: weeks.map(x => x.slice(5)), datasets: Object.entries(hoods.series).map(([name, rows], i) => {
          const m = Object.fromEntries(rows.filter(r => r.n >= 3).map(r => [r.wk, r.m2]));
          return { label: name, data: weeks.map(x => m[x] ?? null), borderColor: SER()[i], backgroundColor: SER()[i], borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .3, spanGaps: true };
        }) },
        options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: true, position: 'top', align: 'start', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } },
          tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${App.usd(c.parsed.y)}` } } },
          scales: { y: { grid: C.grid, ticks: { callback: App.usd } }, x: { grid: C.nogrid, ticks: { maxTicksLimit: 10, maxRotation: 0 } } } } });
      C.vbar('c-age', dom.buckets.map(b => b.bucket), dom.buckets.map(b => b.n), { fmtv: App.fmt, label: 'Listings' });
      const fast = dom.by_area;
      App.table($('t-age'), [{ key: 'name', label: 'Neighbourhood' }, { key: 'median_days', label: 'Median days', num: true, bar: true },
        { key: 'stale_pct', label: 'Stale >90d', num: true, render: v => v + '%' }, { key: 'n', label: 'Listings', num: true, render: App.fmt }], fast);
      const last = w[w.length - 2], first = w.find(r => r.n >= 20) || w[0];
      const ch = last && first ? (last.m2 / first.m2 - 1) * 100 : null;
      const dl = dom.delisting;
      $('t-kpis').innerHTML = [
        ['trending-up', '52-week change', ch == null ? '–' : `<span class="delta ${ch >= 0 ? 'up' : 'down'}">${App.pct(ch)}</span>`, `median USD/m² ${first ? first.wk : ''} → ${last ? last.wk : ''}`],
        ['timer', 'Median days on market', App.fmt(fast.length ? fast.map(r => r.median_days).sort((a, b) => a - b)[Math.floor(fast.length / 2)] : null), 'across neighbourhoods'],
        ['log-out', 'Delisted since last run', dl ? App.fmt(dl.gone) : '–', dl ? `${dl.rate_pct}% of ${App.fmt(dl.prev_n)} (sold, expired or withdrawn) · all types` : 'needs 2+ scrape runs'],
        ['history', 'Scrape runs tracked', App.fmt(t.by_run.length), t.by_run.map(r => r.run).join(' · ')],
      ].map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('');
      App.icons();
    } finally { document.querySelector('.content').classList.remove('loading'); }
  }
  Filters.onChange(load); Filters.init();
})();

(() => {
  const $ = id => document.getElementById(id);
  const ALL = ['ბათუმი', 'ბაკურიანი', 'გუდაური', 'ქობულეთი', 'ბორჯომი', 'სიღნაღი', 'ურეკი', 'თბილისი'];
  let sel = new Set(ALL);
  const SER = () => [C.S.s1, C.S.s2, C.S.s3, C.S.s4, C.S.s5, C.S.s6, '#8a8a94', '#16161a'];
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  function pick() {
    $('r-pick').innerHTML = '<div class="chips">' + ALL.map(c => `<button class="chip ${sel.has(c) ? 'on' : ''}" data-c="${c}">${c}</button>`).join('') + '</div>';
    $('r-pick').querySelectorAll('.chip').forEach(b => b.onclick = () => { sel.has(b.dataset.c) ? sel.delete(b.dataset.c) : sel.add(b.dataset.c); if (!sel.size) sel.add(b.dataset.c); pick(); load(); });
  }
  async function load() {
    const d = await App.api('/api/market/seasonal', { places: [...sel].join(',') });
    C.vbar('c-r-moy', d.month_of_year.map(r => MONTHS[+r.mo - 1]), d.month_of_year.map(r => r.n), { fmtv: App.fmt, label: 'Listings posted' });
    C.hbar('c-r-night', d.by_city.map(r => r.city), d.by_city.map(r => r.median_night), { fmtv: App.usd, label: 'Median / night', color: C.S.s2 });
    const months = [...new Set(d.monthly.map(r => r.m))].sort();
    const places = [...new Set(d.monthly.map(r => r.city))];
    C.draw('c-r-monthly', { type: 'line', data: { labels: months, datasets: places.map((pl, i) => {
        const mm = Object.fromEntries(d.monthly.filter(r => r.city === pl).map(r => [r.m, r.n]));
        return { label: pl, data: months.map(m => mm[m] ?? 0), borderColor: SER()[ALL.indexOf(pl) % 8], backgroundColor: SER()[ALL.indexOf(pl) % 8], borderWidth: 2, pointRadius: 0, tension: .3 }; }) },
      options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: true, position: 'top', align: 'start', labels: { boxWidth: 10, usePointStyle: true } } },
        scales: { y: { grid: C.grid, beginAtZero: true }, x: { grid: C.nogrid, ticks: { maxRotation: 0, maxTicksLimit: 12 } } } } });
    App.table($('t-r-city'), [{ key: 'city', label: 'Place' }, { key: 'n', label: 'Daily-rent listings', num: true, bar: true, render: App.fmt },
      { key: 'median_night', label: 'Median / night', num: true, render: App.usd }, { key: 'p75_night', label: 'p75 / night', num: true, render: App.usd }, { key: 'types', label: 'Types' }], d.by_city);
  }
  App.api('/api/options').then(o => { document.getElementById('snap').textContent = `Snapshot ${o.snapshot} · ${App.fmt(o.total)} clean listings`; });
  pick(); load();
})();

(() => {
  const $ = id => document.getElementById(id);
  const KEY = 'ssge.compare';
  let areas = []; try { areas = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch {}
  let params = null;
  const SER = () => [C.S.s1, C.S.s2, C.S.s3, C.S.s6];

  function picker() {
    const opts = Filters.options(); if (!opts) return;
    const all = Object.entries(opts.districts).flatMap(([d, subs]) => subs.map(s => [d, s]));
    $('cmp-pick').innerHTML = [0, 1, 2, 3].map(i => `<div class="fgroup"><label>Area ${i + 1}</label><select class="ctl" data-i="${i}" style="min-width:190px">
      <option value="">—</option>${Object.keys(opts.districts).map(d => `<optgroup label="${App.esc(d)}">${opts.districts[d].map(s => `<option ${areas[i] === s ? 'selected' : ''}>${App.esc(s)}</option>`).join('')}</optgroup>`).join('')}
      </select></div>`).join('');
    $('cmp-pick').querySelectorAll('select').forEach(s => s.onchange = () => {
      areas[+s.dataset.i] = s.value; areas = areas.slice(0, 4);
      try { localStorage.setItem(KEY, JSON.stringify(areas)); } catch {} load();
    });
    if (!areas.filter(Boolean).length) { areas = all.slice(0, 0); }
  }
  async function load(p) {
    params = p || params; picker();
    const names = areas.filter(Boolean);
    if (!names.length) {
      const top = await App.api('/api/overview/neighbourhoods', new URLSearchParams([...params, ['limit', 4]]));
      areas = top.map(t => t.name); picker(); names.push(...areas);
    }
    const d = await App.api('/api/market/compare', new URLSearchParams([...params, ['areas', names.join(',')]]));
    const rows = [['Listings', 'n', App.fmt], ['Median price', 'median_price', App.compact], ['Median USD/m²', 'median_m2', App.usd],
      ['IQR USD/m²', null, s => `${App.usd(s.p25)} – ${App.usd(s.p75)}`], ['Median area', 'median_area', v => App.fmt(v) + ' m²'],
      ['Median rent', 'median_rent', v => v ? App.usd(v) + '/mo' : '–'], ['Gross yield', 'yield_pct', v => v ? v + '%' : '–'],
      ['New-build share', 'new_build_pct', v => v + '%'], ['Median days listed', 'median_days', App.fmt],
      ['Metro distance', 'metro_km', v => v == null ? '–' : v + ' km'], ['To centre', 'center_km', v => v == null ? '–' : v + ' km']];
    $('cmp-cards').innerHTML = d.stats.map((s, i) => `<div class="card"><div class="card-head"><div><h3><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:${SER()[i]};margin-right:6px"></span>${App.esc(s.name)}</h3></div></div>
      <dl class="kv">${rows.map(([l, k, f]) => `<dt>${l}</dt><dd>${k ? f(s[k]) : f(s)}</dd>`).join('')}</dl></div>`).join('') || '<div class="empty">No data</div>';
    C.draw('c-cmp-m2', { type: 'bar', data: { labels: d.stats.map(s => s.name), datasets: [
        { label: 'IQR', data: d.stats.map(s => [s.p25, s.p75]), backgroundColor: d.stats.map((_, i) => SER()[i] + '44'), borderRadius: 4, borderSkipped: false, barPercentage: .55 },
        { type: 'scatter', label: 'Median', data: d.stats.map(s => ({ x: s.name, y: s.median_m2 })), backgroundColor: d.stats.map((_, i) => SER()[i]), pointRadius: 7, pointStyle: 'rectRot' }] },
      options: { plugins: { tooltip: { callbacks: { label: c => c.dataset.label === 'IQR' ? ` p25–p75 ${App.usd(c.raw[0])} – ${App.usd(c.raw[1])}` : ` median ${App.usd(c.parsed.y)}` } } },
        scales: { y: { grid: C.grid, beginAtZero: true, ticks: { callback: App.usd } }, x: { grid: C.nogrid } } } });
    const rk = ['1', '2', '3', '4', '5+'];
    C.draw('c-cmp-rooms', { type: 'bar', data: { labels: rk.map(r => r + (r === '1' ? ' room' : ' rooms')), datasets: d.stats.map((s, i) => {
        const m = Object.fromEntries(d.rooms.filter(r => r.name === s.name).map(r => [r.r, r.m2]));
        return { label: s.name, data: rk.map(r => m[r] ?? null), backgroundColor: SER()[i], borderRadius: 4, borderSkipped: 'start' }; }) },
      options: { plugins: { legend: { display: true, position: 'bottom', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${App.usd(c.parsed.y)}` } } },
        scales: { y: { grid: C.grid, beginAtZero: true, ticks: { callback: App.usd } }, x: { grid: C.nogrid } } } });
  }
  Filters.onChange(load); Filters.init();
})();

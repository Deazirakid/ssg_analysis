(() => {
  const $ = id => document.getElementById(id);
  const val = k => +document.querySelector(`#i-form [data-k=${k}]`).value || 0;
  const set = (k, v) => { if (v != null) document.querySelector(`#i-form [data-k=${k}]`).value = Math.round(v); };

  function calc() {
    const price = val('price'), down = price * val('down') / 100, loan = price - down;
    const r = val('rate') / 100 / 12, n = val('years') * 12;
    const pay = loan > 0 ? (r ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n) : 0;
    const grossY = val('rent') * 12;
    const effRent = grossY * (1 - val('vac') / 100);
    const noi = effRent * (1 - val('costs') / 100) - effRent * val('tax') / 100;
    const debt = pay * 12, cash = noi - debt;
    const invested = down + val('extra');
    const hold = Math.max(1, Math.round(val('hold')));
    let bal = loan, cum = -invested, value = price; const rows = [];
    for (let y = 1; y <= hold; y++) {
      for (let m = 0; m < 12; m++) { if (bal <= 0) break; const int = bal * r; bal = Math.max(0, bal - (pay - int)); }
      value *= 1 + val('appr') / 100;
      cum += y <= val('years') ? cash : noi;
      rows.push({ y, cum, equity: value - bal, total: cum + (value - bal) });
    }
    const end = rows[rows.length - 1];
    const be = rows.find(x => x.cum >= 0);
    const tiles = [
      ['percent', 'Gross yield', price ? (grossY / price * 100).toFixed(2) + '%' : '–', `net (NOI) ${price ? (noi / price * 100).toFixed(2) : '–'}%`],
      ['landmark', 'Monthly mortgage', App.usd(pay), `loan ${App.compact(loan)} · ${val('years')} y @ ${val('rate')}%`],
      ['wallet', 'Monthly cash flow', `<span class="${cash >= 0 ? 'pos' : 'neg'}">${App.usd(cash / 12)}</span>`, `NOI ${App.usd(noi / 12)} − debt ${App.usd(pay)}`],
      ['target', 'Cash-on-cash return', invested ? (cash / invested * 100).toFixed(1) + '%' : '–', `on ${App.compact(invested)} invested`],
      ['hourglass', 'Cash break-even', be ? `year ${be.y}` : `> ${hold} y`, 'cumulative cash flow ≥ 0'],
      ['trending-up', `Total return (${hold} y)`, App.compact(end.total), `${invested ? ((end.total / invested) * 100).toFixed(0) : '–'}% of cash invested`],
    ];
    $('i-kpis').innerHTML = tiles.map(k => `<div class="card kpi"><div class="label"><span class="chipic"><i data-lucide="${k[0]}"></i></span>${k[1]}</div><div class="value">${k[2]}</div><div class="sub">${k[3]}</div></div>`).join('');
    App.icons();
    C.draw('c-inv', { type: 'line', data: { labels: rows.map(x => 'Y' + x.y), datasets: [
        { label: 'Cumulative cash flow', data: rows.map(x => x.cum), borderColor: C.S.s2, borderWidth: 2, pointRadius: 2 },
        { label: 'Equity', data: rows.map(x => x.equity), borderColor: C.S.s1, borderWidth: 2, pointRadius: 2 },
        { label: 'Total return', data: rows.map(x => x.total), borderColor: C.S.s3, borderWidth: 2.5, pointRadius: 2, fill: { target: 'origin', above: C.S.s3 + '14' } }] },
      options: { interaction: { mode: 'index', intersect: false }, plugins: { legend: { display: true, position: 'top', align: 'start', labels: { boxWidth: 10, usePointStyle: true } },
        tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${App.compact(c.parsed.y)}` } } }, scales: { y: { grid: C.grid, ticks: { callback: App.compact } }, x: { grid: C.nogrid } } } });
  }
  async function loadListing(id) {
    if (!id) return;
    try {
      const d = await App.api('/api/market/invest/' + id);
      const l = d.listing;
      set('price', l.price_usd); set('area', l.area_m2);
      if (d.estimated_rent) set('rent', d.estimated_rent);
      $('i-info').innerHTML = `<b>${App.esc(l.title)}</b> · ${App.esc(l.subdistrict || l.city || '')} · ${App.usd(l.usd_per_m2)}/m² · <a href="${App.esc(l.url)}" target="_blank" rel="noopener">ss.ge ↗</a><br>
        Rent estimate: ${d.rent_same_rooms?.rent ? `median ${App.usd(d.rent_same_rooms.rent)}/mo from ${d.rent_same_rooms.n} same-room rentals` : d.estimated_rent ? `${App.usd(d.estimated_rent)}/mo from area rent/m²` : 'no comparable rentals'}`;
      history.replaceState(null, '', '/invest?id=' + id);
      calc();
    } catch { App.toast('Listing not found in current data'); }
  }
  document.querySelectorAll('#i-form input').forEach(i => i.oninput = calc);
  $('i-load').onclick = () => loadListing($('i-id').value.trim());
  $('i-id').onkeydown = e => { if (e.key === 'Enter') loadListing($('i-id').value.trim()); };
  const id = new URLSearchParams(location.search).get('id');
  if (id) { $('i-id').value = id; loadListing(id); } else calc();
  App.api('/api/options').then(o => { $('snap').textContent = `Snapshot ${o.snapshot} · ${App.fmt(o.total)} clean listings`; });
})();

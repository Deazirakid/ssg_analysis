// Chart.js defaults + small factory helpers (one hue per chart; thin marks; recessive grid).
const C = (() => {
  const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const S = { s1: css('--s1'), s2: css('--s2'), s3: css('--s3'), s4: css('--s4'), s5: css('--s5'), s6: css('--s6'), ink2: css('--ink-2'), ink3: css('--ink-3'), line: css('--line') };
  if (window.Chart) {
    Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 11.5;
    Chart.defaults.color = S.ink2;
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.backgroundColor = '#0f1115';
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.cornerRadius = 8;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation.duration = 250;
  }
  const charts = {};
  const grid = { color: S.line, drawTicks: false }, nogrid = { display: false };
  const money = v => App.compact(v);

  function draw(id, cfg) {
    if (charts[id]) charts[id].destroy();
    const el = document.getElementById(id); if (!el) return;
    charts[id] = new Chart(el, cfg); return charts[id];
  }
  function hbar(id, labels, values, { color = S.s1, fmtv = money, label = '' } = {}) {
    return draw(id, { type: 'bar', data: { labels, datasets: [{ label, data: values, backgroundColor: color, borderRadius: 4, borderSkipped: 'start', barPercentage: .78, categoryPercentage: .9 }] },
      options: { indexAxis: 'y', scales: { x: { grid, beginAtZero: true, ticks: { callback: v => fmtv(v), maxTicksLimit: 6 } }, y: { grid: nogrid, ticks: { autoSkip: false, font: { size: 11 } } } },
        plugins: { tooltip: { callbacks: { label: c => ` ${label ? label + ': ' : ''}${fmtv(c.parsed.x)}` } } } } });
  }
  function vbar(id, labels, values, { color = S.s1, fmtv = money, label = '' } = {}) {
    return draw(id, { type: 'bar', data: { labels, datasets: [{ label, data: values, backgroundColor: color, borderRadius: 4, borderSkipped: 'start', barPercentage: .8, categoryPercentage: .9 }] },
      options: { scales: { y: { grid, beginAtZero: true, ticks: { callback: v => fmtv(v), maxTicksLimit: 6 } }, x: { grid: nogrid } },
        plugins: { tooltip: { callbacks: { label: c => ` ${label ? label + ': ' : ''}${fmtv(c.parsed.y)}` } } } } });
  }
  function line(id, labels, values, { color = S.s1, fmtv = money, label = '' } = {}) {
    return draw(id, { type: 'line', data: { labels, datasets: [{ label, data: values, borderColor: color, borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, tension: .25, fill: { target: 'origin', above: color + '14' } }] },
      options: { interaction: { mode: 'index', intersect: false }, scales: { y: { grid, beginAtZero: true, ticks: { callback: v => fmtv(v), maxTicksLimit: 6 } }, x: { grid: nogrid, ticks: { maxTicksLimit: 8, maxRotation: 0 } } },
        plugins: { tooltip: { callbacks: { label: c => ` ${label}: ${fmtv(c.parsed.y)}` } } } } });
  }
  return { S, draw, hbar, vbar, line, money, grid, nogrid };
})();

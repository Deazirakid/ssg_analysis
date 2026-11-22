(() => {
  const $ = id => document.getElementById(id);
  const kv = (el, obj) => el.innerHTML = Object.entries(obj).map(([k, v]) => `<dt>${App.esc(k)}</dt><dd>${typeof v === 'number' ? App.fmt(v) : App.esc(v ?? '–')}</dd>`).join('');
  let timer;
  async function load() {
    const [st, q, pl] = await Promise.all([App.api('/api/admin/status'), App.api('/api/quality'), App.api('/api/admin/pipeline')]);
    kv($('src'), { Source: st.source.source || 'loading', 'Scrape run': st.source.run, 'Runs in history': st.source.runs, Rows: st.source.rows,
      'Loaded at': st.source.loaded_at, 'Load time': st.source.seconds ? st.source.seconds + ' s' : '–', ...(st.source.error ? { Error: st.source.error } : {}) });
    $('reload').disabled = st.reloading;
    $('pl-hint').textContent = pl.enabled ? 'Enabled on this host (Light Browser available)' : 'Disabled on this host. Set PIPELINE_ENABLED=true on the PC that runs Light Browser.';
    kv($('pl'), { Status: pl.state.running ? 'running…' : 'idle', Started: pl.state.started, Finished: pl.state.finished || pl.last?.finished,
      'Exit code': pl.state.exit ?? pl.last?.exit, Trigger: pl.state.trigger || pl.last?.trigger });
    $('pl-run').disabled = !pl.enabled || pl.state.running;
    $('sc-on').checked = !!pl.schedule.enabled; $('sc-every').value = pl.schedule.every_hours; $('sc-hour').value = pl.schedule.at_hour ?? '';
    $('pl-log').textContent = pl.log || '–';
    const flags = Object.fromEntries(Object.entries(q).filter(([k, v]) => k.startsWith('flag_') && typeof v === 'number').map(([k, v]) => [k.replace('flag_', '').replaceAll('_', ' '), v]));
    kv($('quality'), { 'Raw records': q.total, 'Feed listings': q.feed_listings, 'Clean listings': q.clean, 'Clean in Tbilisi': q.tbilisi_clean, ...flags });
    kv($('precision'), Object.fromEntries((q.precision || []).map(r => [r.coord_precision, r.n])));
    App.table($('t-runs'), [{ key: 'run', label: 'Run' }, { key: 'loaded_at', label: 'Loaded' }, { key: 'listings', label: 'Listings', num: true, render: App.fmt }], st.runs);
    App.table($('t-logins'), [{ key: 'ts', label: 'Time' }, { key: 'event', label: 'Event', render: v => `<span class="badge ${v === 'login_ok' ? 'good' : v === 'logout' ? '' : 'bad'}">${App.esc(v)}</span>` },
      { key: 'username', label: 'User' }, { key: 'ip', label: 'IP' }], st.logins);
    App.table($('t-mix'), [{ key: 'type', label: 'Type' }, { key: 'deal', label: 'Deal' }, { key: 'listings', label: 'Listings', num: true, bar: true, render: App.fmt },
      { key: 'median_price_usd', label: 'Median price', num: true, render: v => App.compact(v) }, { key: 'median_usd_m2', label: 'Median $/m²', num: true, render: App.usd }], q.by_type_deal || []);
    clearTimeout(timer);
    if (st.reloading || pl.state.running) timer = setTimeout(load, 4000);
  }
  $('reload').onclick = async () => { const r = await App.post('/api/admin/reload'); App.toast(r.started ? 'Reloading from MariaDB…' : r.message); setTimeout(load, 1500); };
  $('pl-run').onclick = async () => { await App.post('/api/admin/pipeline/run'); App.toast('Pipeline started'); setTimeout(load, 1500); };
  $('sc-save').onclick = async () => {
    await App.send('PUT', '/api/admin/pipeline/schedule', { enabled: $('sc-on').checked, every_hours: +$('sc-every').value || 24,
      at_hour: $('sc-hour').value === '' ? null : +$('sc-hour').value });
    App.toast('Schedule saved');
  };
  App.api('/api/options').then(o => { $('snap').textContent = `Snapshot ${o.snapshot} · ${App.fmt(o.total)} clean listings`; });
  load();
})();

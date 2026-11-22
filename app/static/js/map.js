(() => {
  const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];
  let layer = 'grid', metric = 'usd_per_m2', cell = 0.004, extrude = false;
  let gridData = null, ptsData = null, breaks = [];
  const $ = id => document.getElementById(id);

  if (!window.MAPBOX_TOKEN) { $('map').innerHTML = '<div class="empty">MAPBOX_TOKEN missing in .env</div>'; return; }
  mapboxgl.accessToken = window.MAPBOX_TOKEN;
  const map = new mapboxgl.Map({ container: 'map', style: (App.isDark && App.isDark()) ? 'mapbox://styles/mapbox/dark-v11' : window.MAPBOX_STYLE, center: [44.80, 41.72], zoom: 11.3, attributionControl: true });
  map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new mapboxgl.FullscreenControl(), 'top-right');
  map.addControl(new mapboxgl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  const ready = new Promise(r => map.on('load', r));

  const quantiles = vals => { const s = [...vals].sort((a, b) => a - b); return [1, 2, 3, 4, 5, 6].map(i => s[Math.floor(s.length * i / 7)] ?? 0); };
  const stepExpr = (prop) => ['step', ['get', prop], RAMP[0], ...breaks.flatMap((b, i) => [b, RAMP[i + 1]])];
  const unit = () => metric === 'usd_per_m2' ? 'USD / m²' : 'total price USD';

  function legend() {
    const el = $('legend');
    if (layer === 'heat') { el.innerHTML = `<b>Listing density</b><div class="ramp">${RAMP.map(c => `<i style="background:${c}"></i>`).join('')}</div><div class="ticks"><span>fewer</span><span>more</span></div>`; return; }
    if (layer === 'clusters') { el.innerHTML = `<b>Clusters</b><div class="meta">Circle size = listing count.<br>Click to zoom in.</div>`; return; }
    const t = [breaks[0], breaks[2], breaks[4], breaks[5]].map(v => App.compact(v));
    el.innerHTML = `<b>Median ${unit()}</b><div class="ramp">${RAMP.map(c => `<i style="background:${c}"></i>`).join('')}</div>
      <div class="ticks"><span>&lt;${t[0]}</span><span>${t[1]}</span><span>${t[2]}</span><span>${t[3]}+</span></div>`;
  }

  function gridGeo(d) {
    const s = d.cell;
    return { type: 'FeatureCollection', features: d.cells.map(c => ({ type: 'Feature',
      properties: { v: c.v, n: c.n, area: c.area },
      geometry: { type: 'Polygon', coordinates: [[[c.gx * s, c.gy * s], [(c.gx + 1) * s, c.gy * s], [(c.gx + 1) * s, (c.gy + 1) * s], [c.gx * s, (c.gy + 1) * s], [c.gx * s, c.gy * s]]] } })) };
  }
  function ptsGeo(d) {
    const i = Object.fromEntries(d.fields.map((f, k) => [f, k]));
    return { type: 'FeatureCollection', features: d.rows.map(r => ({ type: 'Feature',
      properties: { id: r[i.id], price: r[i.price], m2: r[i.m2], area: r[i.area], rooms: r[i.rooms], v: metric === 'usd_per_m2' ? r[i.m2] : r[i.price] },
      geometry: { type: 'Point', coordinates: [r[i.lon], r[i.lat]] } })) };
  }

  function ensureLayers() {
    if (map.getSource('grid')) return;
    map.addSource('grid', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addSource('pts', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addSource('pts-c', { type: 'geojson', data: { type: 'FeatureCollection', features: [] }, cluster: true, clusterRadius: 45, clusterMaxZoom: 15 });
    const before = map.getStyle().layers.find(l => l.type === 'symbol')?.id;
    map.addLayer({ id: 'grid-fill', type: 'fill', source: 'grid', paint: { 'fill-color': RAMP[3], 'fill-opacity': .72, 'fill-outline-color': 'rgba(255,255,255,.6)' } }, before);
    map.addLayer({ id: 'grid-3d', type: 'fill-extrusion', source: 'grid', layout: { visibility: 'none' }, paint: { 'fill-extrusion-color': RAMP[3], 'fill-extrusion-opacity': .85, 'fill-extrusion-height': 0 } });
    map.addLayer({ id: 'heat', type: 'heatmap', source: 'pts', layout: { visibility: 'none' }, paint: {
      'heatmap-weight': 0.08,
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 9, 4, 12, 10, 15, 22],
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 9, .5, 12, 1, 15, 2.5],
      'heatmap-opacity': .85,
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(205,226,251,0)', .15, RAMP[0], .35, RAMP[2], .55, RAMP[3], .75, RAMP[5], 1, RAMP[6]] } }, before);
    map.addLayer({ id: 'pts', type: 'circle', source: 'pts', layout: { visibility: 'none' }, paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 15, 6], 'circle-color': RAMP[3],
      'circle-stroke-color': '#fff', 'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, .3, 15, 1.2], 'circle-opacity': .9 } });
    map.addLayer({ id: 'cl', type: 'circle', source: 'pts-c', filter: ['has', 'point_count'], layout: { visibility: 'none' }, paint: {
      'circle-color': ['step', ['get', 'point_count'], RAMP[2], 50, RAMP[3], 250, RAMP[4], 1000, RAMP[6]],
      'circle-radius': ['step', ['get', 'point_count'], 14, 50, 19, 250, 25, 1000, 32], 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } });
    map.addLayer({ id: 'cl-n', type: 'symbol', source: 'pts-c', filter: ['has', 'point_count'], layout: { visibility: 'none', 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'] }, paint: { 'text-color': '#fff' } });
    map.addLayer({ id: 'cl-pt', type: 'circle', source: 'pts-c', filter: ['!', ['has', 'point_count']], layout: { visibility: 'none' }, paint: { 'circle-color': RAMP[4], 'circle-radius': 5, 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 } });

    // metro stations
    App.api('/api/meta/metro').then(st => {
      map.addSource('metro', { type: 'geojson', data: { type: 'FeatureCollection', features: st.map(s => ({ type: 'Feature', properties: { name: s.name }, geometry: { type: 'Point', coordinates: [s.lon, s.lat] } })) } });
      map.addLayer({ id: 'metro', type: 'circle', source: 'metro', paint: { 'circle-radius': 5, 'circle-color': '#e34948', 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } });
      map.addLayer({ id: 'metro-l', type: 'symbol', source: 'metro', layout: { 'text-field': ['concat', 'Ⓜ ', ['get', 'name']], 'text-size': 11, 'text-offset': [0, 1.2], 'text-anchor': 'top', 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'] },
        paint: { 'text-color': App.isDark() ? '#f0f0f0' : '#7a1d1c', 'text-halo-color': App.isDark() ? '#000' : '#fff', 'text-halo-width': 1.4 } });
      metroVis();
    });
    map.addSource('iso', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
    map.addLayer({ id: 'iso-fill', type: 'fill', source: 'iso', paint: { 'fill-color': '#1baf7a', 'fill-opacity': .14 } });
    map.addLayer({ id: 'iso-line', type: 'line', source: 'iso', paint: { 'line-color': '#1baf7a', 'line-width': 2.5 } });
    const hover = new mapboxgl.Popup({ closeButton: false, closeOnClick: false, offset: 6 });
    ['grid-fill', 'grid-3d'].forEach(id => {
      map.on('mousemove', id, e => { map.getCanvas().style.cursor = 'pointer'; const p = e.features[0].properties;
        hover.setLngLat(e.lngLat).setHTML(`<div class="pop"><div class="price">${metric === 'usd_per_m2' ? App.usd(p.v) + '/m²' : App.compact(p.v)}</div><div class="meta">median of ${App.fmt(p.n)} listings${p.area && p.area !== 'null' ? ` · ${p.area} m² median` : ''}</div></div>`).addTo(map); });
      map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; hover.remove(); });
    });
    ['pts', 'cl-pt'].forEach(id => {
      map.on('mouseenter', id, () => map.getCanvas().style.cursor = 'pointer');
      map.on('mouseleave', id, () => map.getCanvas().style.cursor = '');
      map.on('click', id, e => openListing(e.features[0].properties.id, e.lngLat));
    });
    map.on('click', 'cl', e => {
      const f = e.features[0];
      map.getSource('pts-c').getClusterExpansionZoom(f.properties.cluster_id, (err, z) => { if (!err) map.easeTo({ center: f.geometry.coordinates, zoom: z }); });
    });
    map.on('mouseenter', 'cl', () => map.getCanvas().style.cursor = 'pointer');
    map.on('mouseleave', 'cl', () => map.getCanvas().style.cursor = '');
  }

  async function openListing(id, lngLat) {
    const pop = new mapboxgl.Popup({ offset: 8, maxWidth: '300px' }).setLngLat(lngLat).setHTML('<div class="pop meta">Loading…</div>').addTo(map);
    const l = await App.api('/api/map/listing/' + id);
    pop.setHTML(`<div class="pop"><h5>${App.esc(l.title)}</h5><div class="price">${App.usd(l.price_usd)}</div>
      <div class="meta">${App.usd(l.usd_per_m2)}/m² · ${App.fmt(l.area_m2)} m²${l.rooms ? ` · ${l.rooms} rooms` : ''}${l.floor != null ? ` · floor ${l.floor}/${l.floors_total ?? '?'}` : ''}</div>
      <div class="meta">${App.esc([l.subdistrict, l.street].filter(Boolean).join(', '))}</div>
      <div class="meta">${l.is_project ? '<span class="badge new">New build</span> ' : ''}${l.near_subway ? `Metro: ${App.esc(l.near_subway)} · ` : ''}listed ${App.esc(l.created)}</div>
      <div class="meta">location accuracy: ${App.esc(l.coord_precision)}</div>
      <div class="acts"><a class="btn primary" href="${App.esc(l.url)}" target="_blank" rel="noopener">Open on ss.ge</a>
        <a class="btn" href="/invest?id=${l.id}">Investment calc</a></div></div>`);
  }

  function paint() {
    if (!map.getSource('grid')) return;
    const vis = (ids, on) => ids.forEach(id => map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));
    vis(['grid-fill'], layer === 'grid' && !extrude); vis(['grid-3d'], layer === 'grid' && extrude);
    vis(['heat'], layer === 'heat'); vis(['pts'], layer === 'points'); vis(['cl', 'cl-n', 'cl-pt'], layer === 'clusters');
    if (layer === 'grid' && gridData) {
      breaks = quantiles(gridData.cells.map(c => c.v));
      map.getSource('grid').setData(gridGeo(gridData));
      map.setPaintProperty('grid-fill', 'fill-color', stepExpr('v'));
      map.setPaintProperty('grid-3d', 'fill-extrusion-color', stepExpr('v'));
      const max = Math.max(...gridData.cells.map(c => c.n), 1);
      map.setPaintProperty('grid-3d', 'fill-extrusion-height', ['*', ['/', ['get', 'n'], max], 2500]);
    }
    if (ptsData && layer !== 'grid') {
      const g = ptsGeo(ptsData);
      breaks = quantiles(g.features.map(f => f.properties.v).filter(v => v != null));
      map.getSource('pts').setData(g); map.getSource('pts-c').setData(g);
      map.setPaintProperty('pts', 'circle-color', stepExpr('v'));
    }
    if (extrude && layer === 'grid' && map.getPitch() < 30) map.easeTo({ pitch: 55, bearing: -15 });
    if (!extrude && map.getPitch() > 0) map.easeTo({ pitch: 0, bearing: 0 });
    legend();
  }

  let lastParams = null;
  async function load(p) {
    lastParams = p || lastParams || Filters.params();
    await ready; ensureLayers();
    $('map-loading').style.display = 'block';
    try {
      const q = new URLSearchParams(lastParams);
      if (layer === 'grid') {
        q.set('cell', cell); q.set('metric', metric);
        gridData = await App.api('/api/map/grid', q);
        $('map-count').textContent = `${App.fmt(gridData.cells.length)} cells · ${App.fmt(gridData.cells.reduce((a, c) => a + c.n, 0))} listings`;
      } else {
        ptsData = await App.api('/api/map/points', q);
        $('map-count').textContent = `${App.fmt(ptsData.rows.length)} mapped of ${App.fmt(ptsData.total_filtered)}`;
      }
      paint();
    } finally { $('map-loading').style.display = 'none'; }
  }

  // ---- metro + isochrone ----
  function metroVis() { if (map.getLayer('metro')) ['metro', 'metro-l'].forEach(id => map.setLayoutProperty(id, 'visibility', $('metro').checked ? 'visible' : 'none')); }
  let isoMin = 10;
  const inPoly = (pt, poly) => { let c = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i], [xj, yj] = poly[j];
    if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) c = !c; } return c; };
  async function isochrone(lngLat) {
    const u = `https://api.mapbox.com/isochrone/v1/mapbox/walking/${lngLat.lng},${lngLat.lat}?contours_minutes=${isoMin}&polygons=true&access_token=${mapboxgl.accessToken}`;
    $('map-loading').style.display = 'block';
    try {
      const gj = await (await fetch(u)).json();
      map.getSource('iso').setData(gj);
      const ring = gj.features?.[0]?.geometry?.coordinates?.[0] || [];
      const pts = ptsData || await App.api('/api/map/points', Filters.params());
      ptsData = pts;
      const i = Object.fromEntries(pts.fields.map((f, k) => [f, k]));
      const inside = pts.rows.filter(r => inPoly([r[i.lon], r[i.lat]], ring));
      const m2 = inside.map(r => r[i.m2]).filter(v => v > 0).sort((a, b) => a - b);
      const pr = inside.map(r => r[i.price]).filter(v => v > 0).sort((a, b) => a - b);
      const med = a => a.length ? a[Math.floor(a.length / 2)] : null;
      new mapboxgl.Popup({ offset: 6 }).setLngLat(lngLat).setHTML(`<div class="pop"><h5>${isoMin}-minute walk</h5>
        <div class="price">${App.fmt(inside.length)} listings</div><div class="meta">median ${App.usd(med(m2))}/m² · median price ${App.compact(med(pr))}</div>
        <div class="meta">matches current filters</div></div>`).addTo(map);
    } catch (e) { App.toast('Isochrone failed'); } finally { $('map-loading').style.display = 'none'; }
  }
  map.on('click', e => {
    if (!$('iso').checked) return;
    const hit = map.queryRenderedFeatures(e.point, { layers: ['pts', 'cl', 'cl-pt'].filter(l => map.getLayer(l)) });
    if (!hit.length) isochrone(e.lngLat);
  });
  $('metro').onchange = metroVis;
  $('iso-seg').querySelectorAll('button').forEach(b => b.onclick = () => { $('iso-seg').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); isoMin = +b.dataset.min; });

  const seg = (id, attr, fn) => $(id).querySelectorAll('button').forEach(b => b.onclick = () => {
    $(id).querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); fn(b.dataset[attr]); });
  seg('layer-seg', 'layer', v => { layer = v; load(); });
  seg('metric-seg', 'metric', v => { metric = v; load(); });
  $('cell').onchange = e => { cell = +e.target.value; if (layer === 'grid') load(); };
  $('extrude').onchange = e => { extrude = e.target.checked; paint(); };

  Filters.onChange(load);
  Filters.init();
})();

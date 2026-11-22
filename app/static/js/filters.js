// Global filter bar. State lives in the URL query string (shareable) + localStorage,
// and carries across pages via the sidebar links. Pages subscribe with Filters.onChange(fn).
const Filters = (() => {
  const KEY = 'ssge.filters';
  const DEFAULTS = { type: 'Apartment', deal: 'Sale', region: 'tbilisi' };
  const FIELDS = ['type', 'deal', 'region', 'city', 'district', 'subdistrict', 'rooms', 'price_min', 'price_max',
    'm2_min', 'm2_max', 'area_min', 'area_max', 'floor_min', 'floor_max', 'segment', 'furniture', 'days', 'precision',
    'seller', 'metro_max', 'center_max', 'q'];
  let state = {}, opts = null, subs = [], timer;

  function load() {
    const u = new URLSearchParams(location.search);
    if (FIELDS.some(f => u.has(f))) { FIELDS.forEach(f => { if (u.get(f)) state[f] = u.get(f); }); return; }
    try { state = JSON.parse(localStorage.getItem(KEY) || 'null') || { ...DEFAULTS }; } catch { state = { ...DEFAULTS }; }
  }
  const params = () => { const p = new URLSearchParams(); FIELDS.forEach(f => { if (state[f] !== undefined && state[f] !== '') p.set(f, state[f]); }); return p; };
  function persist() {
    const qs = params().toString();
    history.replaceState(null, '', location.pathname + (qs ? '?' + qs : ''));
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch {}
    document.querySelectorAll('a[data-nav]').forEach(a => a.href = a.pathname + (qs ? '?' + qs : ''));
  }
  function set(k, v, immediate) {
    if (v === '' || v == null || (Array.isArray(v) && !v.length)) delete state[k]; else state[k] = Array.isArray(v) ? v.join(',') : String(v);
    if (k === 'district') delete state.subdistrict;
    persist(); render();
    clearTimeout(timer); timer = setTimeout(() => subs.forEach(fn => fn(params())), immediate ? 0 : 350);
  }
  const list = k => (state[k] || '').split(',').filter(Boolean);

  // ---------- controls ----------
  function multi(key, label, groups, placeholder) {
    const sel = list(key), wrap = document.createElement('div');
    wrap.className = 'fgroup ms'; wrap.innerHTML = `<label>${label}</label>`;
    const btn = document.createElement('button'); btn.type = 'button';
    btn.className = 'ctl' + (sel.length ? ' active' : '');
    btn.textContent = sel.length ? (sel.length === 1 ? sel[0] : `${sel.length} selected`) : placeholder; btn.title = sel.join(', ');
    const pop = document.createElement('div'); pop.className = 'ms-pop';
    const flat = Object.values(groups).flat().length;
    pop.innerHTML = (flat > 8 ? '<input type="search" placeholder="Search…">' : '') +
      Object.entries(groups).map(([g, items]) => (g ? `<div class="ms-grp">${App.esc(g)}</div>` : '') +
        items.map(v => `<label class="ms-opt"><input type="checkbox" value="${App.esc(v)}" ${sel.includes(v) ? 'checked' : ''}>${App.esc(v)}</label>`).join('')).join('') +
      '<div class="ms-actions"><button type="button" data-a="clear">Clear</button><button type="button" data-a="done">Done</button></div>';
    btn.onclick = e => { e.stopPropagation(); document.querySelectorAll('.ms.open').forEach(m => m !== wrap && m.classList.remove('open')); wrap.classList.toggle('open'); const s = pop.querySelector('input[type=search]'); if (s) s.focus(); };
    pop.onclick = e => e.stopPropagation();
    const apply = () => {
      const v = [...pop.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value);
      if (v.join(',') !== list(key).join(',')) set(key, v); else btn.textContent = sel.length ? (sel.length === 1 ? sel[0] : `${sel.length} selected`) : placeholder;
    };
    pop.querySelectorAll('input[type=checkbox]').forEach(c => c.onchange = () => { btn.textContent = '…'; });
    pop.querySelector('[data-a=clear]').onclick = () => { pop.querySelectorAll('input[type=checkbox]').forEach(c => c.checked = false); apply(); };
    pop.querySelector('[data-a=done]').onclick = () => { wrap.classList.remove('open'); apply(); };
    const s = pop.querySelector('input[type=search]');
    if (s) s.oninput = () => pop.querySelectorAll('.ms-opt').forEach(o => o.style.display = o.textContent.toLowerCase().includes(s.value.toLowerCase()) ? '' : 'none');
    wrap._apply = apply;
    wrap.append(btn, pop); return wrap;
  }
  function select(key, label, options) {
    const w = document.createElement('div'); w.className = 'fgroup';
    w.innerHTML = `<label>${label}</label><select class="ctl ${state[key] ? 'active' : ''}">${options.map(([v, t]) => `<option value="${v}" ${(state[key] || '') === v ? 'selected' : ''}>${t}</option>`).join('')}</select>`;
    w.querySelector('select').onchange = e => set(key, e.target.value, true); return w;
  }
  function range(lo, hi, label, ph = ['min', 'max']) {
    const w = document.createElement('div'); w.className = 'fgroup';
    w.innerHTML = `<label>${label}</label><div class="range"><input class="ctl ${state[lo] ? 'active' : ''}" type="number" inputmode="numeric" placeholder="${ph[0]}" value="${state[lo] || ''}"><input class="ctl ${state[hi] ? 'active' : ''}" type="number" inputmode="numeric" placeholder="${ph[1]}" value="${state[hi] || ''}"></div>`;
    const [a, b] = w.querySelectorAll('input');
    a.onchange = () => set(lo, a.value); b.onchange = () => set(hi, b.value); return w;
  }
  function chips(key, label, values) {
    const sel = list(key), w = document.createElement('div'); w.className = 'fgroup';
    w.innerHTML = `<label>${label}</label><div class="chips">${values.map(v => `<button type="button" class="chip ${sel.includes(v) ? 'on' : ''}" data-v="${v}">${v}</button>`).join('')}</div>`;
    w.querySelectorAll('.chip').forEach(c => c.onclick = () => { const s = new Set(list(key)); s.has(c.dataset.v) ? s.delete(c.dataset.v) : s.add(c.dataset.v); set(key, [...s]); });
    return w;
  }
  function search() {
    const w = document.createElement('div'); w.className = 'fgroup';
    w.innerHTML = `<label>Search</label><input class="ctl ${state.q ? 'active' : ''}" type="search" placeholder="Title, street, ID…" value="${App.esc(state.q || '')}" style="min-width:170px">`;
    const i = w.querySelector('input'); i.onchange = () => set('q', i.value.trim()); return w;
  }

  function render() {
    const root = document.getElementById('filters'); if (!root || !opts) return;
    const expanded = root.classList.contains('expanded');
    root.innerHTML = '';
    const tb = state.region !== 'outside';
    const subGroups = {};
    const ds = list('district');
    Object.entries(opts.districts).forEach(([d, subs]) => { if (!ds.length || ds.includes(d)) subGroups[d] = subs; });
    const nActive = FIELDS.filter(f => state[f] && !(f in DEFAULTS && DEFAULTS[f] === state[f])).length;

    root.append(
      multi('type', 'Property', { '': opts.types }, 'All types'),
      multi('deal', 'Deal', { '': opts.deals }, 'All deals'),
      select('region', 'Region', [['tbilisi', 'Tbilisi'], ['all', 'All Georgia'], ['outside', 'Outside Tbilisi']]),
    );
    if (tb) root.append(multi('district', 'District', { '': Object.keys(opts.districts) }, 'All districts'),
                        multi('subdistrict', 'Neighbourhood', subGroups, 'All neighbourhoods'));
    else root.append(multi('city', 'City', { '': opts.cities }, 'All cities'));
    root.append(chips('rooms', 'Rooms', ['1', '2', '3', '4', '5+']),
                range('price_min', 'price_max', 'Price USD'),
                range('m2_min', 'm2_max', 'USD / m²'));

    const more = document.createElement('div'); more.className = 'more';
    more.append(range('area_min', 'area_max', 'Area m²'), range('floor_min', 'floor_max', 'Floor'),
      select('segment', 'Segment', [['', 'Any'], ['new', 'New build / project'], ['resale', 'Resale']]),
      select('furniture', 'Furniture', [['', 'Any'], ['yes', 'Furnished'], ['no', 'Unfurnished']]),
      select('days', 'Listed within', [['', 'Any time'], ['1', '24 hours'], ['7', '7 days'], ['30', '30 days'], ['90', '90 days'], ['365', '1 year']]),
      select('precision', 'Location accuracy', [['', 'Any'], ['precise', 'Exact + street'], ['exact', 'Exact pin only']]),
      select('seller', 'Seller', [['', 'Any'], ['owner', 'Private owner'], ['broker', 'Broker / agency']]),
      range('metro_max', 'center_max', 'Max km to metro · centre', ['metro', 'centre']),
      search());

    const sp = document.createElement('span'); sp.className = 'fspacer';
    const tog = document.createElement('button'); tog.type = 'button'; tog.className = 'btn ghost';
    tog.textContent = expanded ? 'Fewer filters ▲' : 'More filters ▼';
    tog.onclick = () => { root.classList.toggle('expanded'); tog.textContent = root.classList.contains('expanded') ? 'Fewer filters ▲' : 'More filters ▼'; };
    const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'btn';
    reset.textContent = nActive ? `Reset (${nActive})` : 'Reset';
    reset.onclick = () => { state = { ...DEFAULTS }; persist(); render(); subs.forEach(fn => fn(params())); };
    const save = document.createElement('button'); save.type = 'button'; save.className = 'btn';
    save.innerHTML = '<i data-lucide="bookmark-plus"></i>Save search';
    save.onclick = () => saveSearch();
    root.append(sp, tog, save, reset, more);
    App.icons && App.icons();
  }

  function saveSearch() {
    App.modal(`<h3>Save this search</h3><p class="hint" style="margin:0;color:var(--ink-3)">You'll get alerts for new listings and price drops after each data refresh.</p>
      <div class="field"><label>Name</label><input class="input" id="ss-name" placeholder="e.g. Vake 2-room under $150k"></div>
      <label class="ms-opt"><input type="checkbox" id="ss-new" checked>Notify on new listings</label>
      <label class="ms-opt"><input type="checkbox" id="ss-drop" checked>Notify on price drops</label>
      <label class="ms-opt"><input type="checkbox" id="ss-tg">Also send to Telegram (needs TELEGRAM_* in .env)</label>
      <div class="acts"><button class="btn" data-close>Cancel</button><button class="btn primary" id="ss-save">Save</button></div>`, (el, close) => {
      el.querySelector('#ss-name').focus();
      el.querySelector('#ss-save').onclick = async () => {
        const name = el.querySelector('#ss-name').value.trim(); if (!name) return;
        await App.post('/api/alerts/searches', { name, params: Object.fromEntries(params()), notify_new: el.querySelector('#ss-new').checked,
          notify_drops: el.querySelector('#ss-drop').checked, telegram: el.querySelector('#ss-tg').checked });
        close(); App.toast('Search saved');
      };
    });
  }

  document.addEventListener('click', () => document.querySelectorAll('.ms.open').forEach(m => { m.classList.remove('open'); m._apply && m._apply(); }));

  async function init() {
    load(); persist();
    opts = await App.api('/api/options');
    const snap = document.getElementById('snap');
    if (snap) snap.textContent = `Snapshot ${opts.snapshot} · ${App.fmt(opts.total)} clean listings`;
    render();
    subs.forEach(fn => fn(params()));
  }
  return { init, onChange: fn => subs.push(fn), params, get: k => state[k], options: () => opts };
})();

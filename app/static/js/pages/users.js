(() => {
  const $ = id => document.getElementById(id);
  async function load() {
    const [users, keys] = await Promise.all([App.api('/api/admin/users'), App.api('/api/admin/keys')]);
    App.table($('t-users'), [
      { key: 'username', label: 'Username', render: (v, r) => `${App.esc(v)}${r.builtin ? ' <span class="badge blue">.env</span>' : ''}` },
      { key: 'role', label: 'Role', render: v => `<span class="badge ${v === 'admin' ? 'warn' : ''}">${v}</span>` },
      { key: 'active', label: 'Status', render: v => v ? '<span class="badge good">active</span>' : '<span class="badge bad">disabled</span>' },
      { key: 'last_login', label: 'Last login', render: v => v || '–' },
      { key: 'id', label: '', render: (v, r) => r.builtin ? '' : `<button class="btn ghost" data-tog="${v}">${r.active ? 'Disable' : 'Enable'}</button><button class="btn ghost danger" data-del="${v}"><i data-lucide="trash-2"></i></button>` }], users);
    $('t-users').querySelectorAll('[data-tog]').forEach(b => b.onclick = async () => { await App.post(`/api/admin/users/${b.dataset.tog}/toggle`); load(); });
    $('t-users').querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (confirmBox()) { await App.send('DELETE', '/api/admin/users/' + b.dataset.del); load(); } });
    App.table($('t-keys'), [
      { key: 'name', label: 'Name' }, { key: 'prefix', label: 'Key', render: v => `<code>ssk_${v}…</code>` },
      { key: 'role', label: 'Role', render: v => `<span class="badge ${v === 'admin' ? 'warn' : ''}">${v}</span>` },
      { key: 'active', label: 'Status', render: v => v ? '<span class="badge good">active</span>' : '<span class="badge bad">revoked</span>' },
      { key: 'uses', label: 'Uses', num: true, render: App.fmt }, { key: 'last_used', label: 'Last used', render: v => v || '–' },
      { key: 'id', label: '', render: (v, r) => r.active ? `<button class="btn ghost danger" data-rev="${v}">Revoke</button>` : '' }], keys);
    $('t-keys').querySelectorAll('[data-rev]').forEach(b => b.onclick = async () => { await App.post(`/api/admin/keys/${b.dataset.rev}/revoke`); load(); });
    App.icons();
  }
  const confirmBox = () => true; // deletes are explicit button presses; no browser dialogs
  $('u-new').onclick = () => App.modal(`<h3>New account</h3>
    <div class="field"><label>Username</label><input class="input" id="nu-u" autocomplete="off"></div>
    <div class="field"><label>Password (10+ characters)</label><input class="input" id="nu-p" type="password" autocomplete="new-password"></div>
    <div class="field"><label>Role</label><select class="input" id="nu-r"><option value="viewer">Viewer — dashboards only</option><option value="admin">Admin — everything</option></select></div>
    <div class="acts"><button class="btn" data-close>Cancel</button><button class="btn primary" id="nu-go">Create</button></div>`, (el, close) => {
      el.querySelector('#nu-go').onclick = async () => {
        await App.post('/api/admin/users', { username: el.querySelector('#nu-u').value.trim(), password: el.querySelector('#nu-p').value, role: el.querySelector('#nu-r').value });
        close(); App.toast('Account created'); load();
      };
    });
  $('k-new').onclick = () => App.modal(`<h3>New API key</h3>
    <div class="field"><label>Name (what will use it)</label><input class="input" id="nk-n" placeholder="e.g. Google Sheets, mobile app"></div>
    <div class="field"><label>Role</label><select class="input" id="nk-r"><option value="viewer">Viewer — read data endpoints</option><option value="admin">Admin — also admin endpoints</option></select></div>
    <div class="acts"><button class="btn" data-close>Cancel</button><button class="btn primary" id="nk-go">Create key</button></div>`, (el) => {
      el.querySelector('#nk-go').onclick = async () => {
        const r = await App.post('/api/admin/keys', { name: el.querySelector('#nk-n').value.trim(), role: el.querySelector('#nk-r').value });
        el.innerHTML = `<h3>Your new API key</h3><div class="callout warn"><i data-lucide="alert-triangle"></i><div>Copy it now. It won't be shown again.</div></div>
          <div class="code" id="nk-raw">${App.esc(r.key)}</div><div class="acts"><button class="btn" data-close>Done</button><button class="btn primary" id="nk-copy"><i data-lucide="copy"></i>Copy</button></div>`;
        App.icons();
        el.querySelector('[data-close]').onclick = () => document.getElementById('modal').classList.remove('open');
        el.querySelector('#nk-copy').onclick = () => { navigator.clipboard.writeText(r.key); App.toast('Copied'); };
        load();
      };
    });
  $('k-example').textContent = `curl -H "X-API-Key: ssk_YOUR_KEY" "${location.origin}/api/overview/kpis?type=Apartment&deal=Sale&region=tbilisi"

curl -H "X-API-Key: ssk_YOUR_KEY" "${location.origin}/api/market/deals?type=Apartment&deal=Sale&min_discount=20"

# Google Sheets (live):
=IMPORTDATA("${location.origin}/api/export/sheets.csv?api_key=ssk_YOUR_KEY&type=Apartment&deal=Sale")

# Python
import requests
r = requests.get("${location.origin}/api/listings", params={"type": "Apartment", "deal": "Sale", "size": 200},
                 headers={"X-API-Key": "ssk_YOUR_KEY"})
print(r.json()["total"])`;
  App.api('/api/options').then(o => { $('snap').textContent = `Snapshot ${o.snapshot} · ${App.fmt(o.total)} clean listings`; });
  load();
})();

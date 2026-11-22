"""Build output/heatmap.html: interactive Leaflet map of ss.ge prices.

Layers
  - Apartment sale: median USD/m² per ~400 m cell (choropleth grid)
  - Apartment rent: median monthly USD per cell
  - Listing density heat (all clean listings)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
STEP = 0.004  # ~440 m lat x ~330 m lon
MIN_N = 3
BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
ORANGE = ["#fde3d4", "#f9bf9c", "#f39867", "#eb6834", "#c9501f", "#9e3d15", "#702a0c"]


def grid(df, value):
    d = df.dropna(subset=["lat", "lon", value])
    d = d[~d["flag_generic_pin"] & d["coord_precision"].isin(["exact", "street"])]
    d = d.assign(gy=np.floor(d["lat"] / STEP).astype(int), gx=np.floor(d["lon"] / STEP).astype(int))
    g = d.groupby(["gy", "gx"]).agg(n=("id", "size"), v=(value, "median"),
                                    area=("area_m2", "median")).reset_index()
    g = g[g["n"] >= MIN_N]
    return [[int(r.gy), int(r.gx), int(r.n), round(float(r.v)), None if pd.isna(r.area) else round(float(r.area))]
            for r in g.itertuples()]


def breaks(cells):
    v = np.array([c[3] for c in cells])
    return [round(float(x)) for x in np.percentile(v, [100 / 7 * i for i in range(1, 7)])] if len(v) else []


def main():
    df = pd.read_csv(ROOT / "data/clean/listings_clean.csv", low_memory=False)
    sale = df[(df["type"] == "Apartment") & (df["deal"] == "Sale")]
    rent = df[(df["type"] == "Apartment") & (df["deal"] == "Rent")]
    sale_cells, rent_cells = grid(sale, "usd_per_m2"), grid(rent, "price_usd")
    dens = df.dropna(subset=["lat", "lon"])
    dens = dens[~dens["flag_generic_pin"] & dens["coord_precision"].isin(["exact", "street"])][["lat", "lon"]].round(4).values.tolist()
    q = json.loads((ROOT / "data/clean/quality.json").read_text(encoding="utf-8"))

    data = {"step": STEP, "sale": sale_cells, "rent": rent_cells, "dens": dens,
            "saleBreaks": breaks(sale_cells), "rentBreaks": breaks(rent_cells),
            "blue": BLUE, "orange": ORANGE, "run": q["run"], "n": q["clean"]}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    out = ROOT / "output/heatmap.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print("wrote", out, f"({out.stat().st_size/1e6:.1f} MB)", len(sale_cells), "sale cells,",
          len(rent_cells), "rent cells,", len(dens), "points")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ss.ge Price Heatmap</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.heat@0.2.0/dist/leaflet-heat.js"></script>
<style>
:root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e4e3df}
html,body{margin:0;height:100%;font:14px/1.4 system-ui,Segoe UI,sans-serif;background:var(--surface);color:var(--ink)}
#map{position:absolute;inset:56px 0 0 0}
header{height:56px;display:flex;align-items:center;gap:12px;padding:0 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}
header h1{font-size:16px;margin:0}
header .sub{color:var(--ink2);font-size:12px}
.seg{display:flex;gap:4px;margin-left:auto}
.seg button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:6px 10px;cursor:pointer;font:inherit;font-size:13px}
.seg button.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.tiles{filter:grayscale(1) contrast(.9) brightness(1.05)}
.legend{background:#fff;padding:8px 10px;border-radius:6px;box-shadow:0 1px 4px #0002;font-size:12px;color:var(--ink2)}
.legend .row{display:flex;align-items:center;gap:6px}
.legend i{width:18px;height:12px;display:inline-block;border-radius:2px}
@media (max-width:640px){#map{inset:96px 0 0 0}header{height:auto;padding:8px 16px}.seg{margin-left:0}}
</style></head><body>
<header><h1>ss.ge price heatmap</h1><span class="sub" id="sub"></span>
<div class="seg" id="seg">
<button data-l="sale" class="on">Apt sale $/m²</button><button data-l="rent">Apt rent $/mo</button><button data-l="dens">Listing density</button>
</div></header>
<div id="map"></div>
<script>
const D=__DATA__;
document.getElementById('sub').textContent=`${D.n.toLocaleString()} clean listings · run ${D.run} · cells ≈400 m, ${3}+ listings`;
const map=L.map('map',{preferCanvas:true}).setView([41.7151,44.8271],12);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:19,className:'tiles'}).addTo(map);
map.fitBounds([[41.64,44.70],[41.82,44.92]]);
const fmt=n=>n.toLocaleString('en-US');
function colorFor(v,br,ramp){let i=0;while(i<br.length&&v>=br[i])i++;return ramp[i]}
function gridLayer(cells,br,ramp,label,unit){
  const g=L.layerGroup(),s=D.step;
  for(const [gy,gx,n,v,a] of cells){
    L.rectangle([[gy*s,gx*s],[(gy+1)*s,(gx+1)*s]],{stroke:true,weight:1,color:'#fff',opacity:.6,fillColor:colorFor(v,br,ramp),fillOpacity:.72})
     .bindTooltip(`<b>${label}: ${unit==='$/m²'?'$'+fmt(v)+'/m²':'$'+fmt(v)+'/mo'}</b><br>${n} listings${a?` · median ${a} m²`:''}`,{sticky:true})
     .addTo(g);
  }
  g._legend={br,ramp,label,unit};return g;
}
const layers={
  sale:gridLayer(D.sale,D.saleBreaks,D.blue,'Median asking price','$/m²'),
  rent:gridLayer(D.rent,D.rentBreaks,D.orange,'Median monthly rent','$/mo'),
  dens:L.heatLayer(D.dens,{radius:14,blur:18,minOpacity:.25,gradient:{.2:'#cde2fb',.45:'#6da7ec',.7:'#256abf',1:'#0d366b'}})
};
const legend=L.control({position:'bottomright'});
legend.onAdd=()=>{const d=L.DomUtil.create('div','legend');d.id='lg';return d};legend.addTo(map);
function drawLegend(k){
  const el=document.getElementById('lg'),l=layers[k]._legend;
  if(!l){el.innerHTML='<b>Listing density</b><br>darker = more listings';return}
  const b=l.br,rows=l.ramp.map((c,i)=>{const lo=i?b[i-1]:null,hi=b[i];
    const t=lo==null?`< $${fmt(hi)}`:hi==null?`≥ $${fmt(lo)}`:`$${fmt(lo)} – ${fmt(hi)}`;
    return `<div class="row"><i style="background:${c}"></i>${t}</div>`}).reverse().join('');
  el.innerHTML=`<b>${l.label} (${l.unit})</b>${rows}`;
}
let cur=null;
function show(k){if(cur)map.removeLayer(layers[cur]);layers[k].addTo(map);cur=k;drawLegend(k);
  document.querySelectorAll('#seg button').forEach(b=>b.classList.toggle('on',b.dataset.l===k))}
document.getElementById('seg').onclick=e=>{if(e.target.dataset.l)show(e.target.dataset.l)};
show('sale');
</script></body></html>"""

if __name__ == "__main__":
    main()

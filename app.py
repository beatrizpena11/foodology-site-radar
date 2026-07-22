import os, csv, json

# Carga .env si existe (uso en laptop). En Render las llaves van en Environment.
_envfile = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_envfile):
    for _line in open(_envfile, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from flask import Flask, render_template, request, jsonify
import yaml
from radar.providers import get_provider
from radar.engine import discover_gaps, score_locales
from radar.geo import point_radius, haversine_km
from radar.demand import _ANCHORS

BASE = os.path.dirname(__file__)
app = Flask(__name__)

def load_cfg():
    with open(os.path.join(BASE, "config.yaml")) as f:
        return yaml.safe_load(f)

def load_network():
    net = []
    path = os.path.join(BASE, "data", "red_actual.csv")
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("Categoria") != "red_actual":
                continue
            try:
                lat = float(row["Lat"]); lon = float(row["Long"])
            except (ValueError, KeyError):
                continue
            net.append({"nombre": row["Nombre"], "marca": row["Marca"],
                        "tipo": row["Tipo"], "estatus": row["Estatus"],
                        "lat": lat, "lon": lon})
    return net

CFG = load_cfg()
NETWORK = load_network()
PROVIDER = get_provider()
_GAPS = None  # cache en memoria

def name_gap(lat, lon):
    """Nombra el hueco con la zona reconocible mas cercana (<1.8 km);
    si no hay ninguna cerca, usa el nombre de Google."""
    best, bestd = None, 1.8
    for a in _ANCHORS:
        d = haversine_km(lat, lon, a["lat"], a["lon"])
        if d < bestd:
            bestd, best = d, a["name"]
    return best or PROVIDER.reverse_name(lat, lon)

def gaps():
    global _GAPS
    if _GAPS is None:
        try:
            n = CFG.get("huecos", {}).get("top", 7)
            g, _ = discover_gaps(NETWORK, PROVIDER, CFG, top=n * 2)
            for z in g:
                z["nombre"] = name_gap(z["lat"], z["lon"])
            seen, dedup = set(), []
            for z in g:
                if z["nombre"] in seen:
                    continue
                seen.add(z["nombre"]); dedup.append(z)
                if len(dedup) >= n:
                    break
            _GAPS = dedup
        except Exception as e:
            print("error calculando huecos:", e)
            _GAPS = []
    return _GAPS

@app.route("/")
def index():
    net_out = [{**p, "radio_km": point_radius(p, CFG)} for p in NETWORK]
    return render_template("index.html",
        modo=PROVIDER.mode,
        network=json.dumps(net_out),
        gaps=json.dumps(gaps()),
        cfg=json.dumps({"filtros": CFG["filtros"], "pesos": CFG["pesos"]}))

@app.route("/api/score", methods=["POST"])
def api_score():
    text = (request.json or {}).get("locales", "")
    lines = [l for l in text.splitlines() if l.strip()]
    res = score_locales(lines, NETWORK, PROVIDER, CFG)
    return jsonify({"results": res})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global _GAPS
    _GAPS = None
    cache_file = os.path.join(BASE, "cache", "profiles.json")
    try:
        if os.path.exists(cache_file):
            os.remove(cache_file)
    except Exception as e:
        print("no se pudo limpiar cache:", e)
    return jsonify({"gaps": gaps()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

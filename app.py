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

def gaps():
    global _GAPS
    if _GAPS is None:
        g, _ = discover_gaps(NETWORK, PROVIDER, CFG, top=25)
        for z in g:                       # nombra cada hueco (barato)
            z["nombre"] = PROVIDER.reverse_name(z["lat"], z["lon"])
        _GAPS = g
    return _GAPS

@app.route("/")
def index():
    return render_template("index.html",
        modo=PROVIDER.mode,
        network=json.dumps(NETWORK),
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
    return jsonify({"gaps": gaps()})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

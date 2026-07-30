import os, json
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
from radar.engine import discover_gaps_ciudad, score_locales
from radar import nacional

BASE = os.path.dirname(__file__)
app = Flask(__name__)

def load_cfg():
    with open(os.path.join(BASE, "config.yaml")) as f:
        return yaml.safe_load(f)

CFG = load_cfg()
PROVIDER = get_provider()
_GAPS = {}   # cache por ciudad

def ciudad_default():
    return list(nacional.CIUDADES.keys())[0]

def net_ciudad(cid):
    out = []
    for k in nacional.kitchens_ciudad(cid):
        out.append({"nombre": k["nombre"], "marca": "", "tipo": "cocina",
                    "estatus": "activa", "lat": k["lat"], "lon": k["lon"],
                    "radio_km": k["radio_km"]})
    return out

def gaps_ciudad(cid):
    if cid not in _GAPS:
        try:
            _GAPS[cid] = discover_gaps_ciudad(cid, CFG)
        except Exception as e:
            print("error huecos", cid, e); _GAPS[cid] = []
    return _GAPS[cid]

def city_payload(cid):
    c = nacional.CIUDADES[cid]
    return {"id": cid, "nombre": c["nombre"], "centro": c["centro"],
            "zoom": c["zoom"], "nivel": c["nivel"],
            "network": net_ciudad(cid), "gaps": gaps_ciudad(cid)}

@app.route("/")
def index():
    cid = ciudad_default()
    ciudades = [{"id": k, "nombre": v["nombre"]} for k, v in nacional.CIUDADES.items()]
    return render_template("index.html",
        modo=PROVIDER.mode,
        ciudades=json.dumps(ciudades),
        ciudad=json.dumps(city_payload(cid)),
        cfg=json.dumps({"filtros": CFG["filtros"], "pesos": CFG["pesos"]}))

@app.route("/api/ciudad/<cid>")
def api_ciudad(cid):
    if cid not in nacional.CIUDADES:
        return jsonify({"error": "ciudad desconocida"}), 404
    return jsonify(city_payload(cid))

@app.route("/api/score", methods=["POST"])
def api_score():
    text = (request.json or {}).get("locales", "")
    lines = [l for l in text.splitlines() if l.strip()]
    res = score_locales(lines, nacional.KITCHENS, PROVIDER, CFG)
    return jsonify({"results": res})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global _GAPS
    _GAPS = {}
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

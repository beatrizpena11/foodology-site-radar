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
from radar.engine import discover_gaps_ciudad, score_locales, plan_cobertura
from radar import nacional
from radar import apify_locales
import urllib.request as _urlreq
import smtplib
from email.mime.text import MIMEText

BASE = os.path.dirname(__file__)
app = Flask(__name__)

def load_cfg():
    with open(os.path.join(BASE, "config.yaml")) as f:
        return yaml.safe_load(f)

CFG = load_cfg()
PROVIDER = get_provider()
_GAPS = {}   # cache por (ciudad, modo)

def ciudad_default():
    return list(nacional.CIUDADES.keys())[0]

def net_ciudad(cid):
    out = []
    for k in nacional.kitchens_ciudad(cid):
        out.append({"nombre": k["nombre"], "marca": "", "tipo": "cocina",
                    "estatus": "activa", "lat": k["lat"], "lon": k["lon"],
                    "radio_km": k["radio_km"]})
    return out

def _es_coord(nombre):
    return bool(nombre) and (nombre[0].isdigit() or nombre[0] == "-") and "," in nombre

def gaps_ciudad(cid, modo="delivery"):
    key = (cid, modo)
    if key not in _GAPS:
        try:
            g = discover_gaps_ciudad(cid, CFG, modo)
            # nombrar con colonia real (Google) los que quedaron en coordenadas
            for z in g:
                if _es_coord(z.get("nombre", "")):
                    try:
                        nm = PROVIDER.reverse_name(z["lat"], z["lon"])
                        if nm and not _es_coord(nm):
                            z["nombre"] = nm
                    except Exception as e:
                        print("reverse name error:", e)
            _GAPS[key] = g
        except Exception as e:
            print("error huecos", cid, modo, e); _GAPS[key] = []
    return _GAPS[key]

def city_payload(cid, with_gaps=True, modo="delivery"):
    c = nacional.CIUDADES[cid]
    return {"id": cid, "nombre": c["nombre"], "centro": c["centro"],
            "zoom": c["zoom"], "nivel": c["nivel"], "modo": modo,
            "network": net_ciudad(cid),
            "gaps": gaps_ciudad(cid, modo) if with_gaps else []}

@app.route("/")
def index():
    cid = ciudad_default()
    ciudades = [{"id": k, "nombre": v["nombre"]} for k, v in nacional.CIUDADES.items()]
    return render_template("index.html",
        modo=PROVIDER.mode,
        ciudades=json.dumps(ciudades),
        ciudad=json.dumps(city_payload(cid, with_gaps=False)),
        cfg=json.dumps({"filtros": CFG["filtros"], "pesos": CFG["pesos"]}))

@app.route("/api/ciudad/<cid>")
def api_ciudad(cid):
    if cid not in nacional.CIUDADES:
        return jsonify({"error": "ciudad desconocida"}), 404
    modo = request.args.get("modo", "delivery")
    if modo not in ("delivery", "fisico"): modo = "delivery"
    return jsonify(city_payload(cid, modo=modo))

@app.route("/api/plan/<cid>")
def api_plan(cid):
    if cid not in nacional.CIUDADES:
        return jsonify({"error": "ciudad desconocida"}), 404
    modo = request.args.get("modo", "fisico")
    if modo not in ("delivery", "fisico"): modo = "fisico"
    try:
        n = max(1, min(10, int(request.args.get("n", 3))))
    except Exception:
        n = 3
    plan = plan_cobertura(cid, CFG, n, modo)
    # nombrar coords si hiciera falta (reusa el mismo criterio)
    for z in plan:
        if _es_coord(z.get("nombre","")):
            try:
                nm = PROVIDER.reverse_name(z["lat"], z["lon"])
                if nm and not _es_coord(nm): z["nombre"] = nm
            except Exception: pass
    return jsonify({"plan": plan, "n": n, "modo": modo})

@app.route("/api/score", methods=["POST"])
def api_score():
    text = (request.json or {}).get("locales", "")
    lines = [l for l in text.splitlines() if l.strip()]
    res = score_locales(lines, nacional.KITCHENS, PROVIDER, CFG)
    return jsonify({"results": res})



def _evaluar_locales(locales):
    """Geocodifica (si hace falta) y evalua cada local /12 con la logica del radar."""
    res = []
    for L in locales:
        lat, lon = L.get("lat"), L.get("lon")
        if lat is None or lon is None:
            g = PROVIDER.geocode(L.get("direccion") or L.get("titulo") or "")
            if not g:
                continue
            lat, lon = g["lat"], g["lon"]
        # ciudad por bbox
        cid = None
        for c, info in nacional.CIUDADES.items():
            bb = info["bbox"]
            if bb[0] <= lat <= bb[2] and bb[1] <= lon <= bb[3]:
                cid = c; break
        if cid is None:
            continue  # fuera de CDMX/GDL
        kk = nacional.kitchens_ciudad(cid)
        from radar.engine import scores12_nal, _marca_hint_at, recommend_marca
        sc = scores12_nal(lat, lon, cid, kk, "fisico")
        # descuento por cocina cercana (ya lo cubres) salvo punto excepcional comercial
        import math as _m
        def _kmm(a,b,c,d):
            R=6371;p1,p2=_m.radians(a),_m.radians(c)
            return 2*R*_m.asin(_m.sqrt(_m.sin(_m.radians(c-a)/2)**2+_m.cos(p1)*_m.cos(p2)*_m.sin(_m.radians(d-b)/2)**2))
        cerca = min((_kmm(lat,lon,k["lat"],k["lon"]) for k in kk), default=99) < 1.5
        excepc = (sc["c_traf"] == 3 and sc["nse"] >= 0.82)
        if cerca and not excepc and sc["c_nc"] > 1:
            sc["c_nc"] = 1
            sc["total"] = sc["c_dem"] + sc["c_traf"] + sc["c_niv"] + sc["c_nc"]
        marca, _ = recommend_marca({"marca_hint": _marca_hint_at(lat, lon),
                                    "comercial_activity": sc["dem"],
                                    "ingreso_premium": sc["nse"]}, CFG)
        res.append({
            "titulo": L.get("titulo"), "precio": L.get("precio"), "m2": L.get("m2"),
            "direccion": L.get("direccion"), "url": L.get("url"),
            "lat": lat, "lon": lon, "ciudad": nacional.CIUDADES[cid]["nombre"],
            "score": sc["total"], "marca_sugerida": marca,
            "c_dem": sc["c_dem"], "c_traf": sc["c_traf"], "c_niv": sc["c_niv"], "c_nc": sc["c_nc"],
            "nse": sc["nse"],
        })
    res.sort(key=lambda x: x["score"], reverse=True)
    return res


def _guardar_airtable(locales):
    """Guarda los locales rankeados en Airtable (si hay credenciales)."""
    tok = os.environ.get("AIRTABLE_TOKEN"); base = os.environ.get("AIRTABLE_BASE")
    table = os.environ.get("AIRTABLE_TABLE", "Locales")
    if not (tok and base):
        return {"ok": False, "motivo": "faltan AIRTABLE_TOKEN / AIRTABLE_BASE"}
    url = f"https://api.airtable.com/v0/{base}/{table}"
    guardados = 0
    for L in locales[:50]:
        campos = {"Titulo": L["titulo"], "Score": L["score"], "Marca": L["marca_sugerida"],
                  "Precio": L["precio"], "m2": L["m2"], "Direccion": L["direccion"],
                  "Ciudad": L["ciudad"], "URL": L["url"]}
        body = json.dumps({"fields": campos}).encode()
        req = _urlreq.Request(url, data=body, method="POST",
            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        try:
            _urlreq.urlopen(req, timeout=30); guardados += 1
        except Exception as e:
            print("airtable error:", e)
    return {"ok": True, "guardados": guardados}



def _mandar_correo(locales):
    """Manda el top de locales por correo (Gmail app password)."""
    to = os.environ.get("EMAIL_TO"); user = os.environ.get("GMAIL_USER")
    pw = os.environ.get("GMAIL_APP_PASSWORD")
    if not (to and user and pw):
        return {"ok": False, "motivo": "faltan EMAIL_TO / GMAIL_USER / GMAIL_APP_PASSWORD"}
    top = locales[:10]
    filas = "".join(
        f"<tr><td>{i+1}</td><td>{L['titulo'][:40]}</td><td><b>{L['score']}/12</b></td>"
        f"<td>{L['marca_sugerida']}</td><td>{L['ciudad']}</td>"
        f"<td>${(L['precio'] or 0):,.0f}</td><td><a href='{L['url']}'>ver</a></td></tr>"
        for i, L in enumerate(top))
    html = (f"<h2>Locales de la semana — {len(locales)} evaluados</h2>"
            f"<table border=1 cellpadding=6 style='border-collapse:collapse'>"
            f"<tr><th>#</th><th>Local</th><th>Score</th><th>Marca</th><th>Ciudad</th>"
            f"<th>Precio</th><th>Link</th></tr>{filas}</table>"
            f"<p>Radar de Foodology · generado automaticamente</p>")
    msg = MIMEText(html, "html"); msg["Subject"] = f"Radar Foodology: {len(locales)} locales nuevos"
    msg["From"] = user; msg["To"] = to
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
            srv.login(user, pw); srv.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
        return {"ok": True}
    except Exception as e:
        print("correo error:", e); return {"ok": False, "motivo": str(e)[:120]}

@app.route("/api/locales-semana")
def api_locales_semana():
    """Trae locales de Inmuebles24 (via Apify), los evalua y guarda en Airtable."""
    data = apify_locales.traer_locales(max_items=int(request.args.get("max", 40)))
    if "error" in data:
        return jsonify({"error": data["error"]}), 400
    evaluados = _evaluar_locales(data["locales"])
    airtable = _guardar_airtable(evaluados)
    correo = _mandar_correo(evaluados)
    return jsonify({"locales": evaluados, "total": len(evaluados),
                    "airtable": airtable, "correo": correo})

@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    global _GAPS
    _GAPS = {}
    return jsonify({"ok": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

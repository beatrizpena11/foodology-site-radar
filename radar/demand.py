"""Mapa de demanda curado de CDMX (zonas residenciales, de oficina y masivas).

Da, para cualquier punto, un estimado 0-1 de:
  - residente (densidad residencial)
  - flotante  (poblacion de oficina / actividad diurna)
  - premium   (nivel de ingreso)
  - infl      (que tan 'urbana con demanda' es la zona; sirve de filtro anti-bosque)

No son conteos del Censo: son pesos cualitativos por zona real, con caida suave
por distancia. Editable en data/demand_anchors.json.
"""
import os, json, math

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "demand_anchors.json")

def _load():
    with open(_PATH, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("anchors", []), float(d.get("spread_km", 1.4))

_ANCHORS, _SPREAD = _load()

def _km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(a))

def anchor_demand(lat, lon):
    """Combina las zonas cercanas con peso gaussiano por distancia."""
    wsum = res = flot = prem = infl = 0.0
    for a in _ANCHORS:
        d = _km(lat, lon, a["lat"], a["lon"])
        w = math.exp(-(d / _SPREAD) ** 2)      # ~1 en el centro, cae en ~2*spread km
        if w < 0.02:
            continue
        wsum += w
        res  += w * a["res"]
        flot += w * a["flot"]
        prem += w * a["prem"]
        infl = max(infl, w)
    if wsum == 0:
        return {"res": 0.0, "flot": 0.0, "prem": 0.5, "infl": 0.0}
    return {"res": res/wsum, "flot": flot/wsum, "prem": prem/wsum, "infl": infl}

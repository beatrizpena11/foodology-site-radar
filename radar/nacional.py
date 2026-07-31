"""Capa nacional del radar: ciudades, red por ciudad, demanda por ordenes reales,
hubs Turbo y cobertura por poligono real. Todo desde los datos subidos (sin API)."""
import os, json, csv, math
try:
    from shapely.geometry import shape, Point
    _HAS_SHAPELY = True
except Exception:
    _HAS_SHAPELY = False

_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# --- Ciudades disponibles (con datos completos) ---
CIUDADES = {
    "cdmx": {"nombre": "Ciudad de México", "centro": [19.42, -99.15],
             "bbox": [19.15, -99.35, 19.65, -98.95], "zoom": 11, "nivel": True},
    "gdl":  {"nombre": "Guadalajara",      "centro": [20.67, -103.38],
             "bbox": [20.55, -103.55, 20.80, -103.20], "zoom": 11, "nivel": True},
}
def _in_bbox(lat, lon, bb): return bb[0] <= lat <= bb[2] and bb[1] <= lon <= bb[3]

def _km(a, b, c, d):
    R=6371.0; p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

# --- Red de cocinas (real, geolocalizada) ---
def _load_kitchens():
    try:
        raw = json.load(open(os.path.join(_DIR, "kitchens_geo.json"), encoding="utf-8"))
    except Exception:
        return []
    out = []
    for row in raw:
        nombre, lat, lon = row[0], row[1], row[2]
        ciudad = None
        for cid, c in CIUDADES.items():
            if _in_bbox(lat, lon, c["bbox"]): ciudad = cid; break
        radio = 1.5 if "AMSTERDAM" in nombre.upper() or "309" in nombre else 4.0
        out.append({"nombre": nombre, "lat": lat, "lon": lon, "ciudad": ciudad,
                    "radio_km": radio, "poly": None})
    return out
KITCHENS = _load_kitchens()
def kitchens_ciudad(cid): return [k for k in KITCHENS if k["ciudad"] == cid]

# --- Demanda por ordenes reales (RAW DATA) ---
try:
    _ORD = json.load(open(os.path.join(_DIR, "demanda_ordenes.json"), encoding="utf-8"))
except Exception:
    _ORD = []
_OGRID = {}
def _k2(lat, lon): return (round(lat, 2), round(lon, 2))
for o in _ORD:
    _OGRID.setdefault(_k2(o["lat"], o["lon"]), []).append(o)

# escala por ciudad: percentil ~90 de densidad para normalizar 0-1
_SCALE = {}
def _order_sum(lat, lon, radius_km=1.6):
    s = 0.0
    for dla in (-0.02,-0.01,0,0.01,0.02):
        for dlo in (-0.02,-0.01,0,0.01,0.02):
            for o in _OGRID.get((round(lat+dla,2), round(lon+dlo,2)), []):
                d = _km(lat, lon, o["lat"], o["lon"])
                if d <= radius_km:
                    s += o["ord"] * (1 - d/radius_km)
    return s
def _calc_scale(cid):
    c = CIUDADES[cid]; bb = c["bbox"]; vals = []
    la = bb[0]
    while la <= bb[2]:
        lo = bb[1]
        while lo <= bb[3]:
            v = _order_sum(la, lo)
            if v > 0: vals.append(v)
            lo += 0.02
        la += 0.02
    vals.sort()
    return vals[int(len(vals)*0.9)] if vals else 1.0
def order_demand_at(lat, lon, cid):
    if cid not in _SCALE: _SCALE[cid] = _calc_scale(cid)
    sc = _SCALE[cid] or 1.0
    return min(1.0, _order_sum(lat, lon) / sc)

# --- Hubs Turbo (factor positivo) ---
try:
    _HUBS = json.load(open(os.path.join(_DIR, "hubs_turbo.json"), encoding="utf-8"))
except Exception:
    _HUBS = []
def hub_cerca(lat, lon, radius_km=1.5):
    for h in _HUBS:
        if _km(lat, lon, h["lat"], h["lon"]) <= radius_km: return True
    return False

def hub_count(lat, lon, radius_km=2.5):
    return sum(1 for h in _HUBS if _km(lat, lon, h["lat"], h["lon"]) <= radius_km)

# --- Cobertura por poligono real (map 11) + fallback 3 km ---
def _load_polys():
    polys = []
    if not _HAS_SHAPELY:
        return polys
    p = os.path.join(_DIR, "cobertura_poligonos.csv")
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            gj = r.get("_geojson")
            if not gj: continue
            try:
                feat = json.loads(gj)
                polys.append(shape(feat["geometry"]))
            except Exception:
                pass
    except Exception:
        pass
    return polys
_POLYS = _load_polys()

def _match_polys_to_kitchens():
    """Asigna a cada cocina el poligono real cuyo punto-tienda este a <0.8 km."""
    if not _HAS_SHAPELY:
        return
    pts = []  # (lat, lon, geom) del punto de cada poligono
    p = os.path.join(_DIR, "cobertura_poligonos.csv")
    try:
        for r in csv.DictReader(open(p, encoding="utf-8")):
            gj = r.get("_geojson")
            if not gj: continue
            try:
                feat = json.loads(gj)
                pts.append((float(feat["properties"]["STORE_LAT"]),
                            float(feat["properties"]["STORE_LNG"]),
                            shape(feat["geometry"])))
            except Exception:
                pass
    except Exception:
        return
    for k in KITCHENS:
        best, bd = None, 0.8
        for (la, lo, geom) in pts:
            d = _km(k["lat"], k["lon"], la, lo)
            if d < bd: bd, best = d, geom
        k["poly"] = best
def coverage_at(lat, lon, city_kitchens):
    cov = 0.0
    for k in city_kitchens:
        d = _km(lat, lon, k["lat"], k["lon"])
        if d < k["radio_km"]:
            cov = max(cov, 1 - d/k["radio_km"])
    return cov

# --- nombre por microzona de ordenes mas cercana ---
def nearest_micro(lat, lon, radius_km=1.6):
    best, bd = None, radius_km
    for o in _ORD:
        if not o.get("micro"): continue
        d = _km(lat, lon, o["lat"], o["lon"])
        if d < bd: bd, best = d, o["micro"]
    if best:
        import re
        best = re.sub(r"^(CDMX|GDL|MTY)\s*\d*\s*", "", best).strip()  # quita prefijo operativo
    return best

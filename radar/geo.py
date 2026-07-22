"""Geometria basica: distancias, malla y cobertura por captacion."""
import math

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))

def build_grid(bbox, grid_km):
    lat_mid = (bbox["lat_min"] + bbox["lat_max"]) / 2
    dlat = grid_km / 111.0
    dlon = grid_km / (111.0 * math.cos(math.radians(lat_mid)))
    cells = []; cid = 0; lat = bbox["lat_min"]
    while lat <= bbox["lat_max"]:
        lon = bbox["lon_min"]
        while lon <= bbox["lon_max"]:
            cells.append({"id": cid, "lat": round(lat, 6), "lon": round(lon, 6)})
            cid += 1; lon += dlon
        lat += dlat
    return cells

def default_radius(cfg):
    return cfg.get("captacion_km", {}).get("default", 3.0)

def point_radius(p, cfg):
    """Radio de cobertura de un punto. Todos = default (3 km), salvo los turbo
    listados en config (p.ej. Amsterdam = 1.5 km)."""
    turbo = cfg.get("turbo", {}) or {}
    name = (p.get("nombre") or "").strip()
    if name in turbo:
        return float(turbo[name])
    return default_radius(cfg)

def coverage_at(lat, lon, network, cfg):
    best = 0.0
    for p in network:
        r = point_radius(p, cfg)
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        c = max(0.0, 1.0 - d / r)
        if c > best:
            best = c
    return best

def overlap_fraction(lat, lon, network, cfg):
    r_new = default_radius(cfg)
    worst = 0.0
    for p in network:
        r_old = point_radius(p, cfg)
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        sep = d / (r_new + r_old) if (r_new + r_old) > 0 else 1
        ov = max(0.0, 1.0 - sep)
        if ov > worst:
            worst = ov
    return worst

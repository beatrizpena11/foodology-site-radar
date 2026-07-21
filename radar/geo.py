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
    """Devuelve lista de celdas {id, lat, lon} cubriendo la caja."""
    # 1 grado lat ~ 111 km; lon ajustado por coseno de la latitud media
    lat_mid = (bbox["lat_min"] + bbox["lat_max"]) / 2
    dlat = grid_km / 111.0
    dlon = grid_km / (111.0 * math.cos(math.radians(lat_mid)))
    cells = []
    cid = 0
    lat = bbox["lat_min"]
    while lat <= bbox["lat_max"]:
        lon = bbox["lon_min"]
        while lon <= bbox["lon_max"]:
            cells.append({"id": cid, "lat": round(lat, 6), "lon": round(lon, 6)})
            cid += 1
            lon += dlon
        lat += dlat
    return cells

def catchment_radius(tipo, captacion):
    return captacion.get((tipo or "").strip().lower(), captacion.get("default", 2.0))

def coverage_at(lat, lon, network, captacion):
    """Cobertura 0-1 en un punto: 1 = totalmente cubierto por la red propia.
    Decaimiento lineal dentro del radio de captacion de cada punto; se toma el maximo."""
    best = 0.0
    for p in network:
        r = catchment_radius(p.get("tipo"), captacion)
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        c = max(0.0, 1.0 - d / r)
        if c > best:
            best = c
    return best

def overlap_fraction(lat, lon, tipo, network, captacion):
    """Estima el % de traslape de captacion de un local candidato con la red existente.
    Se usa para la penalizacion por canibalizacion."""
    r_new = catchment_radius(tipo, captacion)
    worst = 0.0
    for p in network:
        r_old = catchment_radius(p.get("tipo"), captacion)
        d = haversine_km(lat, lon, p["lat"], p["lon"])
        # fraccion de solape aproximada: cuanto se meten los radios
        sep = d / (r_new + r_old) if (r_new + r_old) > 0 else 1
        ov = max(0.0, 1.0 - sep)
        if ov > worst:
            worst = ov
    return worst

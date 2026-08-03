"""Conexion con Apify: corre el scraper de Inmuebles24 (locales comerciales en renta),
recibe los listings, y los deja listos para evaluar con el radar.

Config por variables de entorno (se pegan en Render, NO en el codigo):
  APIFY_TOKEN       -> tu token de Apify (apify_api_...)
  APIFY_ACTOR       -> id del actor, ej "azzouzana~inmuebles24-scraper-pro-by-search-url"
  INMUEBLES24_URL   -> tu URL de busqueda ya filtrada (locales en renta, tu zona/precio)
"""
import os, json, urllib.request, urllib.error

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_ACTOR = os.environ.get("APIFY_ACTOR", "azzouzana~inmuebles24-scraper-pro-by-search-url")
INMUEBLES24_URL = os.environ.get("INMUEBLES24_URL", "")


def _post(url, payload, timeout=280):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def traer_locales(max_items=50):
    """Corre el actor de Apify (sincrono) y devuelve los listings normalizados.
    Devuelve lista de dicts: {titulo, precio, m2, direccion, url, lat, lon}."""
    if not APIFY_TOKEN:
        return {"error": "Falta APIFY_TOKEN en las variables de entorno de Render."}
    if not INMUEBLES24_URL:
        return {"error": "Falta INMUEBLES24_URL (tu URL de busqueda de Inmuebles24)."}

    # endpoint que corre el actor y regresa los items en una sola llamada
    endpoint = (f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
                f"/run-sync-get-dataset-items?token={APIFY_TOKEN}")
    # input para azzouzana/inmuebles24-scraper-pro-by-search-url: usa "startUrl" (singular)
    payload = {
        "startUrl": INMUEBLES24_URL,
        "maxItems": max_items,
    }
    try:
        items = _post(endpoint, payload)
    except urllib.error.HTTPError as e:
        return {"error": f"Apify respondio {e.code}: {e.read().decode('utf-8')[:300]}"}
    except Exception as e:
        return {"error": f"No pude conectar con Apify: {e}"}

    return {"locales": [_normaliza(x) for x in items if isinstance(x, dict)]}


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = "".join(c for c in str(v) if c.isdigit() or c == ".")
    try:
        return float(s) if s else None
    except Exception:
        return None


def _normaliza(x):
    """Mapea campos del scraper a un formato estable (los nombres varian por actor)."""
    def pick(*keys):
        for k in keys:
            if k in x and x[k] not in (None, ""):
                return x[k]
        return None
    lat = _num(pick("lat", "latitude", "latitud"))
    lon = _num(pick("lng", "lon", "longitude", "longitud"))
    # a veces la ubicacion viene anidada
    loc = pick("location", "coordinates", "geo")
    if (lat is None or lon is None) and isinstance(loc, dict):
        lat = lat or _num(loc.get("lat") or loc.get("latitude"))
        lon = lon or _num(loc.get("lng") or loc.get("lon") or loc.get("longitude"))
    return {
        "titulo": pick("title", "titulo", "name") or "Local sin titulo",
        "precio": _num(pick("price", "precio", "rentPrice")),
        "m2": _num(pick("area", "m2", "surface", "totalArea", "coveredArea")),
        "direccion": pick("address", "direccion", "location_text", "ubicacion") or "",
        "url": pick("url", "link", "listingUrl", "permalink") or "",
        "lat": lat, "lon": lon,
    }

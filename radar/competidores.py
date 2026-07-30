"""Competencia cercana (Ojo de Agua, Green Grass, Mora Mora, Toks, Sushi Itto...)."""
import os, json, math

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "competidores.json")
try:
    _COMP = json.load(open(_PATH, encoding="utf-8")).get("competidores", [])
except Exception:
    _COMP = []

def _km(a,b,c,d):
    R=6371.0; p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

def competitors_near(lat, lon, radius_km=1.2):
    """Devuelve marcas distintas y total de sucursales dentro del radio."""
    marcas=set(); total=0
    for c in _COMP:
        if _km(lat,lon,c["lat"],c["lon"])<=radius_km:
            marcas.add(c["marca"]); total+=1
    return {"marcas": len(marcas), "sucursales": total, "lista": sorted(marcas)}

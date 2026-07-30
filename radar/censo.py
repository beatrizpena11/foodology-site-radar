"""Poblacion y nivel socioeconomico reales por punto (Censo 2020 INEGI, por AGEB).

Carga TODOS los archivos data/ageb_*.json (CDMX, Jalisco, y los que se agreguen).
census_at(lat,lon) -> {pob, nse 0-1, estrato 1-3, cubierto}.
El estrato es relativo dentro de cada ciudad (tercios), comparable como nivel 1-3.
"""
import os, json, math, glob

_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_AGEB = []
for path in glob.glob(os.path.join(_DIR, "ageb_*.json")):
    try:
        _AGEB.extend(json.load(open(path, encoding="utf-8")))
    except Exception as e:
        print("no pude cargar", path, e)

_GRID = {}
def _key(lat, lon): return (round(lat, 2), round(lon, 2))
for a in _AGEB:
    _GRID.setdefault(_key(a["lat"], a["lon"]), []).append(a)

def _km(a, b, c, d):
    R=6371.0; p1,p2=math.radians(a),math.radians(c)
    dp=math.radians(c-a); dl=math.radians(d-b)
    x=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*R*math.asin(math.sqrt(x))

def census_at(lat, lon, radius_km=1.2):
    near=[]
    for dla in (-0.02,-0.01,0,0.01,0.02):
        for dlo in (-0.02,-0.01,0,0.01,0.02):
            near.extend(_GRID.get((round(lat+dla,2), round(lon+dlo,2)), []))
    pob=0.0; wsum=0.0; nse=0.0; estr=0.0
    for a in near:
        d=_km(lat,lon,a["lat"],a["lon"])
        if d>radius_km: continue
        w=1.0-d/radius_km
        pob+=a["pob"]*w
        wp=a["pob"]*w
        nse+=a["nse"]*wp
        estr+=a["estrato"]*wp
        wsum+=wp
    if wsum==0:
        return {"pob":0,"nse":0.0,"estrato":0,"cubierto":False}
    return {"pob":int(pob),"nse":round(nse/wsum,3),
            "estrato":int(round(estr/wsum)),"cubierto":True}

def ciudades_cargadas():
    return len(_AGEB)

"""Proveedores de datos.

LiveProvider   -> Google Maps (geocode + Places). INEGI DENUE es OPCIONAL.
SampleProvider -> datos sinteticos para ver la herramienta sin llaves.

Arranca EN VIVO si hay GOOGLE_MAPS_API_KEY. Si ademas hay INEGI_TOKEN, enriquece
con negocios del DENUE; si no, usa Google Places como proxy de demanda.
"""
import os, math, json, hashlib
import urllib.request, urllib.parse

def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "foodology-radar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _post_json(url, payload, headers, timeout=12):
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}; h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


class SampleProvider:
    mode = "muestra"
    HOT = [(19.4270,-99.1677,1.0),(19.4333,-99.1930,1.0),(19.4127,-99.1710,0.9),
           (19.3700,-99.2600,0.85),(19.3900,-99.1730,0.7),(19.3550,-99.1620,0.6),
           (19.3050,-99.1270,0.4)]
    PREMIUM = [(19.4333,-99.1930,1.0),(19.4127,-99.1710,0.85),(19.3700,-99.2600,0.8),
               (19.4270,-99.1677,0.75),(19.6000,-99.2900,0.7)]
    def _field(self, lat, lon, anchors, spread=0.06):
        return sum(a[2]*math.exp(-((lat-a[0])**2+(lon-a[1])**2)/(2*spread**2)) for a in anchors)
    def geocode(self, address):
        h = int(hashlib.md5(address.encode()).hexdigest(), 16)
        return {"lat": round(19.30+(h%1000)/1000*0.28,6),
                "lon": round(-99.28+((h//1000)%1000)/1000*0.22,6),
                "formatted": address+" (geocode muestra)"}
    def reverse_name(self, lat, lon): return f"Zona {lat:.3f},{lon:.3f}"
    def zone_profile(self, lat, lon, radius_km=1.0):
        act = min(1.0, self._field(lat,lon,self.HOT)); prem = min(1.0,self._field(lat,lon,self.PREMIUM))
        return {"flotante":act,"negocios":act*0.9,
                "residente":min(1.0,0.35+0.5*self._field(lat,lon,self.HOT,0.10)),
                "comercial_activity":act,"ingreso_premium":prem,
                "competencia_total":act*40,"competencia_directa":act*6,
                "oficina_share":min(1.0,0.3+0.5*act)}


class LiveProvider:
    def __init__(self, google_key, inegi_token=None):
        self.gk = google_key
        self.it = (inegi_token or "").strip() or None
        self._inegi_ok = bool(self.it)   # se apaga solo si falla una vez
        # INEGI cambio su endpoint; hasta repararlo, el modo es Google.
        self.mode = "en vivo (Google)"

    def geocode(self, address):
        u = ("https://maps.googleapis.com/maps/api/geocode/json?address="
             + urllib.parse.quote(address) + "&region=mx&key=" + self.gk)
        try:
            d = _get_json(u)
            if d.get("status") == "OK":
                r = d["results"][0]; loc = r["geometry"]["location"]
                return {"lat": loc["lat"], "lon": loc["lng"],
                        "formatted": r.get("formatted_address", address)}
        except Exception as e:
            print("geocode error:", e)
        return None

    def reverse_name(self, lat, lon):
        u = (f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}"
             f"&language=es&key={self.gk}")
        prefer = ["neighborhood", "sublocality_level_1", "sublocality",
                  "locality", "administrative_area_level_3",
                  "administrative_area_level_2"]
        try:
            d = _get_json(u)
            if d.get("status") == "OK" and d.get("results"):
                # junta todos los componentes de los primeros resultados
                comps = []
                for res in d["results"][:5]:
                    comps.extend(res.get("address_components", []))
                for t in prefer:
                    for c in comps:
                        if t in c.get("types", []):
                            return c["long_name"]
                # ultimo recurso: primera parte de la direccion formateada
                fa = d["results"][0].get("formatted_address", "")
                if fa:
                    return fa.split(",")[0][:40]
        except Exception as e:
            print("reverse error:", e)
        return f"{lat:.3f},{lon:.3f}"

    def _places(self, lat, lon, radius_km):
        try:
            body = {"includedTypes":["restaurant"],"maxResultCount":20,
                    "locationRestriction":{"circle":{
                        "center":{"latitude":lat,"longitude":lon},
                        "radius":min(2000,radius_km*1000)}}}
            headers = {"X-Goog-Api-Key":self.gk,"X-Goog-FieldMask":"places.priceLevel"}
            d = _post_json("https://places.googleapis.com/v1/places:searchNearby",body,headers)
            places = d.get("places",[])
            plm = {"PRICE_LEVEL_INEXPENSIVE":0.25,"PRICE_LEVEL_MODERATE":0.5,
                   "PRICE_LEVEL_EXPENSIVE":0.8,"PRICE_LEVEL_VERY_EXPENSIVE":1.0}
            prices=[plm[p["priceLevel"]] for p in places if p.get("priceLevel") in plm]
            return len(places), (sum(prices)/len(prices) if prices else 0.5)
        except Exception as e:
            print("places error:", e); return 0, 0.5

    def _denue(self, lat, lon, radius_km):
        if not self.it or not self._inegi_ok:
            return None
        u = (f"https://www.inegi.org.mx/app/api/denue/v1/consulta/Buscar/todos/"
             f"{lat},{lon}/{int(radius_km*1000)}/{self.it}")
        try:
            rows = _get_json(u, timeout=6)
            if isinstance(rows, list):
                return {"negocios": len(rows)}
            self._inegi_ok = False   # respuesta rara -> apagar INEGI
            return None
        except Exception as e:
            print("denue caido, se desactiva por esta sesion:", e)
            self._inegi_ok = False   # una sola falla y ya no se vuelve a llamar
            return None

    def zone_profile(self, lat, lon, radius_km=1.0):
        from .demand import anchor_demand
        n_rest, premium_g = self._places(lat, lon, radius_km)
        dens = min(1.0, n_rest/20.0)              # densidad comercial (Google)
        a = anchor_demand(lat, lon)               # residencial/oficina/premium (curado)
        active = max(dens, a["infl"])             # filtro: zona urbana con demanda real
        den = self._denue(lat, lon, radius_km)
        negocios = min(1.0, den["negocios"]/400.0) if den else dens
        return {"flotante": max(a["flot"], dens), "negocios": negocios,
                "residente": a["res"], "comercial_activity": dens,
                "ingreso_premium": max(premium_g, a["prem"]),
                "competencia_total": n_rest, "competencia_directa": n_rest,
                "oficina_share": 0.3, "_active": active,
                "marca_hint": a.get("marca")}


def get_provider():
    gk = os.environ.get("GOOGLE_MAPS_API_KEY","").strip()
    it = os.environ.get("INEGI_TOKEN","").strip()
    if gk:
        return LiveProvider(gk, it)
    return SampleProvider()

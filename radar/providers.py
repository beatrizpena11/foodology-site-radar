"""Proveedores de datos.

LiveProvider  -> Google Maps (geocode + competencia) + INEGI DENUE (empleo/negocios).
SampleProvider-> datos sinteticos deterministas para ver la herramienta sin llaves.

La app elige automaticamente: si hay GOOGLE_MAPS_API_KEY e INEGI_TOKEN en el
entorno usa el modo en vivo; si no, usa el modo muestra.
"""
import os, math, json, hashlib
import urllib.request, urllib.parse

# ---------- utilidades ----------
def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "foodology-radar/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def _post_json(url, payload, headers, timeout=20):
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}; h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

ESTRATO_MID = {  # personal ocupado -> punto medio para estimar empleo (flotante)
    "0 a 5": 3, "6 a 10": 8, "11 a 30": 20, "31 a 50": 40,
    "51 a 100": 75, "101 a 250": 175, "251 y m": 350,
}
def _estrato_headcount(s):
    s = (s or "").lower()
    for k, v in ESTRATO_MID.items():
        if k.lower() in s:
            return v
    return 5

OFICINA_KW = ["financ", "seguros", "corporativ", "profesional", "cientific",
              "tecnic", "inmobiliar", "informaci", "consultor", "juridic", "contab"]
COMIDA_KW = ["restaurant", "alimento", "comida", "cafeter", "antojito", "preparaci"]


class SampleProvider:
    """Datos sinteticos: varian de forma realista por la ciudad (mas demanda y
    oficinas en el centro/Reforma/Polanco/Santa Fe; periferia mas baja)."""
    mode = "muestra"

    HOT = [  # (lat, lon, peso) polos de actividad
        (19.4270, -99.1677, 1.0),  # Reforma/Juarez (oficinas)
        (19.4333, -99.1930, 1.0),  # Polanco (premium)
        (19.4127, -99.1710, 0.9),  # Roma/Condesa
        (19.3700, -99.2600, 0.85), # Santa Fe (oficinas)
        (19.3900, -99.1730, 0.7),  # Del Valle / Insurgentes
        (19.3550, -99.1620, 0.6),  # Narvarte
        (19.3050, -99.1270, 0.4),  # Coapa sur
    ]
    PREMIUM = [(19.4333, -99.1930, 1.0), (19.4127, -99.1710, 0.85),
               (19.3700, -99.2600, 0.8), (19.4270, -99.1677, 0.75),
               (19.6000, -99.2900, 0.7)]  # Interlomas/Lomas

    def _field(self, lat, lon, anchors, spread=0.06):
        v = 0.0
        for a in anchors:
            d2 = (lat - a[0])**2 + (lon - a[1])**2
            v += a[2] * math.exp(-d2 / (2 * spread**2))
        return v

    def geocode(self, address):
        h = int(hashlib.md5(address.encode()).hexdigest(), 16)
        lat = 19.30 + (h % 1000) / 1000 * 0.28
        lon = -99.28 + ((h // 1000) % 1000) / 1000 * 0.22
        return {"lat": round(lat, 6), "lon": round(lon, 6),
                "formatted": address + " (geocode muestra)"}

    def reverse_name(self, lat, lon):
        return f"Zona {lat:.3f},{lon:.3f}"

    def zone_profile(self, lat, lon, radius_km=1.0):
        act = self._field(lat, lon, self.HOT)
        prem = self._field(lat, lon, self.PREMIUM)
        flot = min(1.0, act)
        neg = min(1.0, act * 0.9)
        res = min(1.0, 0.35 + 0.5 * self._field(lat, lon, self.HOT, spread=0.10))
        comp_total = act * 40
        comp_directa = act * 6
        return {
            "flotante": flot, "negocios": neg, "residente": res,
            "comercial_activity": min(1.0, act),
            "ingreso_premium": min(1.0, prem),
            "competencia_total": comp_total, "competencia_directa": comp_directa,
            "oficina_share": min(1.0, 0.3 + 0.5 * act),
        }


class LiveProvider:
    """Google Maps + INEGI DENUE. Se activa con las llaves en el entorno."""
    mode = "en vivo"

    def __init__(self, google_key, inegi_token, censo=None):
        self.gk = google_key
        self.it = inegi_token
        self.censo = censo or {}   # opcional: {(cell)->poblacion} si se carga Censo

    # ---- Google ----
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
             f"&result_type=neighborhood|sublocality&key={self.gk}")
        try:
            d = _get_json(u)
            if d.get("status") == "OK" and d["results"]:
                return d["results"][0].get("formatted_address", f"{lat:.3f},{lon:.3f}")
        except Exception as e:
            print("reverse error:", e)
        return f"{lat:.3f},{lon:.3f}"

    def _places_competition(self, lat, lon, radius_km):
        """Cuenta restaurantes cercanos y estima nivel de precios (premium)."""
        try:
            body = {"includedTypes": ["restaurant"],
                    "maxResultCount": 20,
                    "locationRestriction": {"circle": {
                        "center": {"latitude": lat, "longitude": lon},
                        "radius": min(50000, radius_km * 1000)}}}
            headers = {"X-Goog-Api-Key": self.gk,
                       "X-Goog-FieldMask": "places.priceLevel,places.rating"}
            d = _post_json("https://places.googleapis.com/v1/places:searchNearby",
                           body, headers)
            places = d.get("places", [])
            n = len(places)
            pl_map = {"PRICE_LEVEL_INEXPENSIVE": 0.25, "PRICE_LEVEL_MODERATE": 0.5,
                      "PRICE_LEVEL_EXPENSIVE": 0.8, "PRICE_LEVEL_VERY_EXPENSIVE": 1.0}
            prices = [pl_map.get(p.get("priceLevel"), 0.5) for p in places if p.get("priceLevel")]
            premium = sum(prices)/len(prices) if prices else 0.5
            return n, premium
        except Exception as e:
            print("places error:", e)
            return 0, 0.5

    def _denue(self, lat, lon, radius_km):
        """DENUE Buscar: establecimientos en el radio. Estima empleo y oficinas."""
        metros = int(radius_km * 1000)
        u = (f"https://www.inegi.org.mx/app/api/denue/v1/consulta/Buscar/todos/"
             f"{lat},{lon}/{metros}/{self.it}")
        try:
            rows = _get_json(u)
        except Exception as e:
            print("denue error:", e)
            return {"negocios": 0, "empleo": 0, "oficina": 0, "comida": 0}
        if not isinstance(rows, list):
            return {"negocios": 0, "empleo": 0, "oficina": 0, "comida": 0}
        empleo = ofi = com = 0
        for r in rows:
            clase = str(r.get("Clase_actividad") or r.get("nombre_act") or "").lower()
            estr = str(r.get("Estrato") or r.get("estrato") or "")
            hc = _estrato_headcount(estr)
            empleo += hc
            if any(k in clase for k in OFICINA_KW):
                ofi += 1
            if any(k in clase for k in COMIDA_KW):
                com += 1
        return {"negocios": len(rows), "empleo": empleo, "oficina": ofi, "comida": com}

    def zone_profile(self, lat, lon, radius_km=1.0):
        den = self._denue(lat, lon, radius_km)
        n_rest, premium = self._places_competition(lat, lon, radius_km)
        # normalizaciones suaves (se recalibran con datos reales)
        flot = min(1.0, den["empleo"] / 4000.0)
        neg = min(1.0, den["negocios"] / 400.0)
        res = float(self.censo.get(_cell_key(lat, lon), 0.0))  # 0 si no hay Censo
        oficina_share = (den["oficina"] / den["negocios"]) if den["negocios"] else 0.0
        return {
            "flotante": flot, "negocios": neg, "residente": res,
            "comercial_activity": min(1.0, (den["negocios"] + n_rest) / 400.0),
            "ingreso_premium": premium,
            "competencia_total": den["comida"] + n_rest,
            "competencia_directa": den["comida"],
            "oficina_share": oficina_share,
        }


def _cell_key(lat, lon):
    return f"{round(lat,3)},{round(lon,3)}"

def get_provider():
    gk = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    it = os.environ.get("INEGI_TOKEN", "").strip()
    if gk and it:
        return LiveProvider(gk, it)
    return SampleProvider()

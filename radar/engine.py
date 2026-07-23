"""Motor del radar: demanda, huecos, marca sugerida y scoring de locales."""
import os, json, math
from .geo import build_grid, coverage_at, overlap_fraction, haversine_km

CACHE = os.path.join(os.path.dirname(__file__), "..", "cache", "profiles.json")


def _load_cache():
    try:
        with open(CACHE) as f: return json.load(f)
    except Exception: return {}

def _save_cache(d):
    try:
        with open(CACHE, "w") as f: json.dump(d, f)
    except Exception as e: print("cache save:", e)

def _norm(vals):
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9: return [0.0 for _ in vals]
    return [(v - lo) / (hi - lo) for v in vals]


def recommend_marca(prof, cfg):
    hint = prof.get("marca_hint")
    if hint:
        return (hint, "Marca que Foodology define para esta zona (editable en demand_anchors).")
    com = prof["comercial_activity"]; prem = prof["ingreso_premium"]
    m = cfg["marca"]
    if com < m["darkkitchen_max_comercial"]:
        return ("Dark kitchen",
                "Zona de baja actividad comercial y renta tipicamente menor: "
                "ideal para cocina de reparto, no para retail.")
    if prem >= m["avocalia_min_ingreso"]:
        return ("Avocalia",
                "Zona premium y muy concurrida, con perfil de ingreso alto y "
                "cliente de oficina: encaja el formato top con retail visible.")
    return ("Green House",
            "Zona comercial de perfil medio con fuerte flujo de oficina entre "
            "semana: encaja el formato masivo y accesible.")


def discover_gaps(network, provider, cfg, scan_km=None, top=None):
    """Barre todo CDMX, calcula demanda vs cobertura y devuelve huecos rankeados."""
    if scan_km is None:
        scan_km = cfg["ciudad"].get("scan_km", 3.0)
    if top is None:
        top = cfg.get("huecos", {}).get("top", 7)
    agrupar_km = cfg.get("huecos", {}).get("agrupar_km", 2.75)
    bbox = cfg["ciudad"]["bbox"]
    dm = cfg["demanda"]
    cells = build_grid(bbox, scan_km)
    cache = _load_cache()
    raw = []
    for c in cells:
        key = f"{round(c['lat'],3)},{round(c['lon'],3)}"
        prof = cache.get(key)
        if prof is None:
            prof = provider.zone_profile(c["lat"], c["lon"], radius_km=scan_km/2)
            cache[key] = prof
        cov = coverage_at(c["lat"], c["lon"], network, cfg)
        demand_raw = (dm["peso_flotante"] * prof["flotante"]
                      + dm["peso_negocios"] * prof["negocios"]
                      + dm["peso_residente"] * prof["residente"])
        # gradiente por cercania real a la demanda -> evita empates en 1.00
        grad = 0.55 + 0.45 * prof.get("_active", 1.0)
        raw.append({"cell": c, "prof": prof, "cov": cov,
                    "demand_raw": demand_raw * grad})
    _save_cache(cache)

    gate = cfg["demanda"].get("gate_min", 0.12)
    for r in raw:
        active = r["prof"].get("_active", 1.0)   # sample no trae _active -> no filtra
        dem = min(1.0, r["demand_raw"])          # demanda real (sin comprimir)
        r["demand"] = dem if active >= gate else 0.0   # filtro anti-bosque/pueblo
        r["gap"] = r["demand"] * (1.0 - r["cov"])   # alta demanda + baja cobertura

    raw.sort(key=lambda r: r["gap"], reverse=True)

    # agrupa celdas-hueco contiguas en zonas (merge greedy <1.2 km)
    zones = []
    for r in raw:
        if r["gap"] < 0.12:  # ignora ruido de baja demanda
            continue
        placed = False
        for z in zones:
            if haversine_km(r["cell"]["lat"], r["cell"]["lon"],
                            z["lat"], z["lon"]) < agrupar_km:
                z["members"].append(r); placed = True; break
        if not placed:
            zones.append({"lat": r["cell"]["lat"], "lon": r["cell"]["lon"],
                          "members": [r]})
        if len(zones) >= top * 2:
            pass

    out = []
    for z in zones:
        best = max(z["members"], key=lambda r: r["gap"])
        prof = best["prof"]
        marca, why = recommend_marca(prof, cfg)
        out.append({
            "lat": round(best["cell"]["lat"], 5),
            "lon": round(best["cell"]["lon"], 5),
            "gap": round(best["gap"], 3),
            "demanda": round(best["demand"], 3),
            "cobertura": round(best["cov"], 3),
            "flotante": round(prof["flotante"], 2),
            "residente": round(prof["residente"], 2),
            "premium": round(prof["ingreso_premium"], 2),
            "marca_sugerida": marca, "porque": why,
            "nombre": None,  # se rellena con reverse_name en la app (barato)
        })
    out.sort(key=lambda z: z["gap"], reverse=True)
    return out[:top], raw


# ---------------- scoring de locales pegados ----------------
def _parse_line(line):
    """Acepta: 'Direccion | m2=120 | renta=150000 | gas=si | extraccion=si | url=...'
    renta puede ser total mensual (renta=) o por m2 (renta_m2=)."""
    parts = [p.strip() for p in line.split("|")]
    d = {"direccion": parts[0], "m2": None, "renta_total": None,
         "renta_m2": None, "gas": None, "extraccion": None, "url": None}
    for p in parts[1:]:
        if "=" not in p: continue
        k, v = [x.strip().lower() for x in p.split("=", 1)]
        if k == "m2": d["m2"] = _num(v)
        elif k in ("renta", "renta_total"): d["renta_total"] = _num(v)
        elif k == "renta_m2": d["renta_m2"] = _num(v)
        elif k == "gas": d["gas"] = v in ("si", "sí", "yes", "true", "1")
        elif k in ("extraccion", "extracción"): d["extraccion"] = v in ("si","sí","yes","true","1")
        elif k == "url": d["url"] = p.split("=",1)[1].strip()
    return d

def _num(v):
    try: return float("".join(ch for ch in v if ch.isdigit() or ch == "."))
    except Exception: return None


def score_locales(lines, network, provider, cfg):
    filt = cfg["filtros"]; pesos = cfg["pesos"]
    dm = cfg["demanda"]; canib = cfg["canibalizacion"]
    results = []
    for line in lines:
        if not line.strip(): continue
        loc = _parse_line(line)
        geo = provider.geocode(loc["direccion"])
        if not geo:
            results.append({"direccion": loc["direccion"], "estado": "no_geolocalizado",
                            "score": None, "motivos": ["No se pudo ubicar la direccion."]})
            continue
        lat, lon = geo["lat"], geo["lon"]
        motivos = []; descartes = []

        # ---- filtros duros ----
        if loc["m2"] is not None and not (filt["m2_min"] <= loc["m2"] <= filt["m2_max"]):
            descartes.append(f"m2 fuera de rango ({loc['m2']:.0f}; pide {filt['m2_min']}-{filt['m2_max']}).")
        renta_m2 = loc["renta_m2"]
        if renta_m2 is None and loc["renta_total"] and loc["m2"]:
            renta_m2 = loc["renta_total"] / loc["m2"]
        if renta_m2 is not None and renta_m2 > filt["renta_max_m2"]:
            descartes.append(f"renta ${renta_m2:.0f}/m2 supera el tope (${filt['renta_max_m2']}).")
        if loc["gas"] is False:
            descartes.append("sin gas (obligatorio).")
        if loc["extraccion"] is False:
            descartes.append("sin salida de extraccion (obligatorio).")

        prof = provider.zone_profile(lat, lon, radius_km=1.0)
        cov = coverage_at(lat, lon, network, cfg)
        # marca sugerida para decidir radio de captacion del candidato
        marca, why = recommend_marca(prof, cfg)
        tipo = "dark kitchen" if marca == "Dark kitchen" else "storefront"

        # ---- componentes 0-1 ----
        # ajuste m2/renta: mejor si renta baja y tamano medio; neutral si faltan datos
        if renta_m2 is not None:
            s_renta = max(0.0, min(1.0, 1 - renta_m2 / filt["renta_max_m2"]))
        else:
            s_renta = 0.5; motivos.append("Sin renta -> componente m2/renta en neutral.")
        s_zona = (dm["peso_flotante"]*prof["flotante"] + dm["peso_negocios"]*prof["negocios"]
                  + dm["peso_residente"]*prof["residente"])
        s_hueco = 1.0 - cov
        # competencia: algo de competencia es bueno (valida demanda), saturacion penaliza
        ct = prof["competencia_total"]
        s_comp = math.exp(-((ct - 15) ** 2) / (2 * 18 ** 2))  # optimo ~15 restaurantes
        # adecuaciones: gas/extraccion ya son filtro; aqui viabilidad restante
        s_adec = 0.7
        if loc["gas"] and loc["extraccion"]: s_adec = 0.9

        base = (pesos["ajuste_m2_renta"]*s_renta + pesos["calidad_zona"]*s_zona
                + pesos["cobertura_hueco"]*s_hueco + pesos["competencia"]*s_comp
                + pesos["adecuaciones"]*s_adec)  # 0-100

        # ---- canibalizacion (penalizacion dura) ----
        ov = overlap_fraction(lat, lon, network, cfg)
        canibaliza = ov >= canib["umbral_solape"]
        if canibaliza:
            if canib["modo"] == "excluir":
                descartes.append(f"canibaliza red propia (solape {ov:.0%}).")
            else:
                base *= canib["factor_penalizacion"]
                motivos.append(f"Penalizado por canibalizacion (solape {ov:.0%} con red propia).")

        estado = "descartado" if descartes else "candidato"
        score = None if descartes else round(base, 1)
        results.append({
            "direccion": geo.get("formatted", loc["direccion"]),
            "lat": lat, "lon": lon, "estado": estado, "score": score,
            "marca_sugerida": marca, "porque_marca": why,
            "cobertura": round(cov, 2), "demanda": round(s_zona, 2),
            "componentes": {"m2_renta": round(s_renta,2), "zona": round(s_zona,2),
                            "hueco": round(s_hueco,2), "competencia": round(s_comp,2),
                            "adecuaciones": round(s_adec,2)},
            "motivos": motivos, "descartes": descartes, "url": loc["url"],
        })
    results.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    return results

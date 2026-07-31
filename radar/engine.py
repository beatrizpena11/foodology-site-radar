"""Motor del radar: demanda, huecos, marca sugerida y scoring de locales."""
import os, json, math
from .geo import build_grid, coverage_at, overlap_fraction, haversine_km
from .censo import census_at
from .competidores import competitors_near

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
    prem = prof.get("ingreso_premium", 0.5)
    if prem >= 0.75:
        return ("Avocalia", "Zona de nivel alto.")
    if prem >= 0.55:
        return ("Green House", "Zona de nivel medio.")
    return ("Dark kitchen", "Zona de nivel bajo: mejor solo delivery.")
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


def net_uncovered_pct(lat, lon, network, cfg, radius_km=3.0, n=240):
    """% del área del hueco (~3 km) que NO cubre tu red actual (hueco neto).
    Descuenta lo que ya alcanza una cocina existente."""
    import random
    unc = 0
    for _ in range(n):
        ang = random.random() * 2 * math.pi
        rr = radius_km * math.sqrt(random.random())
        dlat = rr / 111.0 * math.cos(ang)
        dlon = rr / (111.0 * math.cos(math.radians(lat))) * math.sin(ang)
        if coverage_at(lat + dlat, lon + dlon, network, cfg) < 0.2:
            unc += 1
    return round(100 * unc / n)


def scores12(lat, lon, prof, cov, cfg):
    """Score estilo /12 = Foot Traffic + Poblacion/Nivel + Competencia + No-canibalizacion.
    Cada componente 1-3. Datos reales: nivel del Censo, competencia de sucursales."""
    # Foot Traffic (actividad/demanda diurna) 1-3
    act = max(prof.get("comercial_activity", 0.0), prof.get("flotante", 0.0))
    ft = 3 if act >= 0.5 else (2 if act >= 0.2 else 1)
    # Poblacion / nivel socioeconomico real (Censo) 1-3
    cen = census_at(lat, lon)
    estrato = cen["estrato"] or 1
    # Competencia cercana: presencia valida la demanda 1-3
    ci = competitors_near(lat, lon)
    comp = 3 if ci["marcas"] >= 2 else (2 if ci["marcas"] == 1 else 1)
    # No-canibalizacion 1-3 (3 = sin traslape con red propia)
    nc = 3 if cov < 0.15 else (2 if cov < 0.5 else 1)
    total = ft + estrato + comp + nc
    return {"ft": ft, "pop": estrato, "comp": comp, "canib": nc, "total": total,
            "pob": cen["pob"], "nse": cen["nse"], "competidores": ci}


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
        dem = min(1.0, r["demand_raw"])
        r["demand"] = dem if active >= gate else 0.0   # filtro anti-bosque/pueblo
        r["gap"] = r["demand"] * (1.0 - r["cov"])

    # candidatas que pasan el filtro anti-bosque; se puntuan /12
    from .demand import vetoed
    cand = [r for r in raw if r["demand"] > 0 and r["gap"] >= 0.05
            and not vetoed(r["cell"]["lat"], r["cell"]["lon"])]
    for r in cand:
        r["s12"] = scores12(r["cell"]["lat"], r["cell"]["lon"], r["prof"], r["cov"], cfg)
    cand.sort(key=lambda r: (r["s12"]["total"], r["gap"]), reverse=True)

    # agrupa celdas-hueco vecinas en zonas grandes
    zones = []
    for r in cand:
        placed = False
        for z in zones:
            if haversine_km(r["cell"]["lat"], r["cell"]["lon"],
                            z["lat"], z["lon"]) < agrupar_km:
                z["members"].append(r); placed = True; break
        if not placed:
            zones.append({"lat": r["cell"]["lat"], "lon": r["cell"]["lon"],
                          "members": [r]})

    out = []
    for z in zones:
        best = max(z["members"], key=lambda r: r["s12"]["total"])
        prof = best["prof"]; s = best["s12"]
        marca, why = recommend_marca(prof, cfg)
        la, lo = round(best["cell"]["lat"], 5), round(best["cell"]["lon"], 5)
        out.append({
            "lat": la, "lon": lo,
            "total": s["total"], "ft": s["ft"], "pop": s["pop"],
            "comp": s["comp"], "canib": s["canib"],
            "pob": s["pob"], "nse": s["nse"],
            "competidores": s["competidores"]["lista"],
            "cobertura": round(best["cov"], 2), "gap": round(best["gap"], 3),
            "neto_pct": net_uncovered_pct(la, lo, network, cfg),
            "marca_sugerida": marca, "porque": why, "nombre": None,
        })
    out.sort(key=lambda z: z["total"], reverse=True)
    return (out if (top is None or top <= 0) else out[:top]), raw


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
    """Evalua SOLO la direccion, con las mismas variables del mapa (score /12):
    FT (ordenes+poblacion), Nivel (Censo), Restaurantes parecidos, No-canibalizacion,
    + bono Turbo si hay hub. Detecta la ciudad sola. Sin gas/extraccion/m2/renta."""
    from . import nacional
    results = []
    for line in lines:
        addr = line.split("|")[0].strip()   # por si pegan datos extra, tomamos la direccion
        if not addr:
            continue
        geo = provider.geocode(addr)
        if not geo:
            results.append({"direccion": addr, "estado": "no_geolocalizado",
                            "score": None, "motivos": ["No se pudo ubicar la dirección."]})
            continue
        lat, lon = geo["lat"], geo["lon"]
        # detectar ciudad por bbox
        cid = None
        for c, info in nacional.CIUDADES.items():
            bb = info["bbox"]
            if bb[0] <= lat <= bb[2] and bb[1] <= lon <= bb[3]:
                cid = c; break
        kk = nacional.kitchens_ciudad(cid) if cid else nacional.KITCHENS
        s = scores12_nal(lat, lon, cid or list(nacional.CIUDADES)[0], kk)
        marca, why = recommend_marca({"marca_hint": _marca_hint_at(lat, lon),
                                      "comercial_activity": s["dem"],
                                      "ingreso_premium": s["nse"]}, cfg)
        results.append({
            "direccion": geo.get("formatted", addr), "lat": lat, "lon": lon,
            "estado": "candidato", "score": s["total"],
            "marca_sugerida": marca, "porque_marca": why,
            "ciudad": nacional.CIUDADES[cid]["nombre"] if cid else "fuera de ciudades con datos",
            "cobertura": s["cov"], "pob": s["pob"], "nse": s["nse"], "hub": s["hub"],
            "neto_pct": net_uncovered_pct_nal(lat, lon, kk),
            "competidores": s["competidores"],
            "componentes": {"ft": s["ft"], "pop": s["pop"],
                            "comp": s["comp"], "canib": s["canib"]},
            "motivos": [], "descartes": [],
        })
    results.sort(key=lambda r: (r["score"] is not None, r["score"] or 0), reverse=True)
    return results


# ==================== MOTOR NACIONAL (por ciudad) ====================
def _nombre_hueco_nal(lat, lon):
    """Nombra por: 1) zona nombrada cercana, 2) microzona del RAW DATA, 3) coords."""
    from .demand import _ANCHORS
    best, bd = None, 3.5
    for a in _ANCHORS:
        d = haversine_km(lat, lon, a["lat"], a["lon"])
        if d < bd: bd, best = d, a["name"]
    if best: return best
    try:
        from .nacional import nearest_micro
        m = nearest_micro(lat, lon, 3.5)
        if m: return m
    except Exception:
        pass
    return f"{lat:.3f},{lon:.3f}"


def _marcar_canibalizacion(zonas, radio_km=4.0):
    """Agrupa huecos que se canibalizan entre si (<radio_km) y les pone
    'grupo' (id) y 'alternativas' (nombres de los otros del grupo)."""
    grupos = []  # cada grupo = lista de indices
    for i, z in enumerate(zonas):
        col = None
        for g in grupos:
            if any(haversine_km(z["lat"], z["lon"], zonas[j]["lat"], zonas[j]["lon"]) < radio_km for j in g):
                col = g; break
        if col is None:
            grupos.append([i])
        else:
            col.append(i)
    for gid, g in enumerate(grupos):
        if len(g) > 1:
            for idx in g:
                zonas[idx]["grupo"] = gid + 1
                zonas[idx]["alternativas"] = [zonas[j]["nombre"] for j in g if j != idx]
        else:
            zonas[g[0]]["grupo"] = None
            zonas[g[0]]["alternativas"] = []
    return zonas

def scores12_nal(lat, lon, cid, city_kitchens, modo='delivery'):
    """Score /12 nacional: FT(ordenes) + Nivel(censo) + Parecidos + No-canib, + bono hub."""
    from . import nacional
    from .censo import census_at
    from .competidores import competitors_near
    # FT = demanda de mercado: max(ordenes reales, poblacion residente)
    dem = nacional.order_demand_at(lat, lon, cid)
    cen = census_at(lat, lon)
    pob_norm = min(1.0, cen["pob"]/8000.0)
    ftsig = max(dem, pob_norm)
    ft = 3 if ftsig >= 0.5 else (2 if ftsig >= 0.2 else 1)
    niv = cen["estrato"] or 1
    # Restaurantes parecidos (valida que la zona pide comida)
    ci = competitors_near(lat, lon)
    par = 3 if ci["marcas"] >= 2 else (2 if ci["marcas"] == 1 else 1)
    # Cobertura (poligono real o 3 km) -> No-canibalizacion
    cov = nacional.coverage_at(lat, lon, city_kitchens)
    nc = 3 if cov < 0.15 else (2 if cov < 0.5 else 1)
    # Hub Turbo cercano -> bono chico + etiqueta
    hub = nacional.hub_cerca(lat, lon)
    if modo == "fisico":
        # PUNTO FISICO: manda el NIVEL FINO (nse continuo). Las zonas top
        # (Lomas, Tecamachalco, Pedregal, San Jeronimo) suben; el trafico solo desempata.
        total = round(min(12, cen["nse"] * 11 + min(ft, 2) * 0.15))
        rank = min(12, cen["nse"] * 11) + (0.5 if hub else 0)
    else:
        # DELIVERY / DARK KITCHEN
        base = ft + niv + par + nc
        mult = {3: 1.0, 2: 0.7, 1: 0.35}.get(niv, 0.35)
        total = round(base * mult)
        rank = base * mult + (0.5 if hub else 0)
    return {"ft": ft, "pop": niv, "comp": par, "canib": nc, "total": total,
            "rank": rank, "hub": hub, "dem": round(dem, 2), "cov": round(cov, 2),
            "pob": cen["pob"], "nse": cen["nse"], "competidores": ci["lista"]}

def discover_fisico(cid, cfg):
    """Punto fisico: barre la ciudad por CELDAS y evalua el nivel PROMEDIO del AREA
    (no un AGEB suelto). Solo zonas donde TODA el area es de nivel alto (nse>=0.85)
    y sin cocina propia dentro. Rankea por nivel."""
    from . import nacional
    from .censo import census_at
    from .competidores import competitors_near
    c = nacional.CIUDADES[cid]; bb = c["bbox"]
    kk = nacional.kitchens_ciudad(cid)
    step = 0.012
    cand = []
    la = bb[0]
    while la <= bb[2]:
        lo = bb[1]
        while lo <= bb[3]:
            cen = census_at(la, lo)                 # nivel PROMEDIO del area (~1.2 km)
            # estandar real (calibrado con Samara/Londres/Amsterdam/Manacar): nivel medio-alto
            if cen["nse"] >= 0.72 and cen["pob"] > 0:
                mind = min((haversine_km(la, lo, k["lat"], k["lon"]) for k in kk), default=99)
                # señal comercial: hay restaurantes (corredor con trafico) o densidad de ordenes
                from .competidores import competitors_near as _cn
                trafico = (_cn(la, lo)["marcas"] >= 1 or nacional.order_demand_at(la, lo, cid) >= 0.15
                           or nacional.hub_count(la, lo) >= 1)
                if mind > 2.5 and trafico:
                    cand.append({"lat": la, "lon": lo, "nse": cen["nse"],
                                 "pob": cen["pob"], "estrato": cen["estrato"]})
            lo += step
        la += step
    cand.sort(key=lambda z: z["nse"], reverse=True)
    # agrupar zonas separadas >2.5 km, quedandose con la de mayor nivel
    zonas = []
    for z in cand:
        if any(haversine_km(z["lat"], z["lon"], w["lat"], w["lon"]) < 2.5 for w in zonas):
            continue
        zonas.append(z)
    out = []
    for z in zonas:
        la, lo, nse = z["lat"], z["lon"], z["nse"]
        ci = competitors_near(la, lo)
        nhub = nacional.hub_count(la, lo, 3.0)
        # STOREFRONT (0-6): nivel + BONO DE OFICINAS/TRAFICO (hubs+restaurantes).
        #   el Censo mide nivel residencial y subvalua zonas de oficina (Lomas, Sta Fe);
        #   el bono corrige eso: mucha actividad = poder adquisitivo real mas alto.
        oficina = min(1.5, nhub * 0.25 + ci["marcas"] * 0.3)           # hasta +1.5
        store_pts = max(3.0, min(6.0, 3 + (nse - 0.72) / 0.26 * 3 + oficina))
        deliv_pts = min(6.0, 1 + nhub * 1.7)                           # 1-6 por delivery
        total = round(min(12, store_pts + deliv_pts))
        nombre = _nombre_hueco_nal(la, lo)
        hint = _marca_hint_at(la, lo)
        marca = hint or ("Avocalia" if nse >= 0.86 else "Green House")
        out.append({"lat": round(la, 5), "lon": round(lo, 5), "nombre": nombre,
                    "total": total, "ft": 0, "pop": z["estrato"],
                    "comp": ci["marcas"], "canib": 3, "hub": nacional.hub_cerca(la, lo),
                    "pob": z["pob"], "nse": round(nse, 3), "cobertura": 0.0,
                    "neto_pct": net_uncovered_pct_nal(la, lo, kk),
                    "competidores": ci["lista"], "marca_sugerida": marca,
                    "porque": "Area de nivel alto sin cocina propia; apta para punto fisico."})
    out.sort(key=lambda z: z["total"], reverse=True)
    seen, ded = set(), []
    for z in out:
        if z["nombre"] in seen: continue
        seen.add(z["nombre"]); ded.append(z)
    return ded


def discover_gaps_ciudad(cid, cfg, modo='delivery'):
    fis_all = discover_fisico(cid, cfg)
    # PUNTO FISICO = solo buenos storefronts (score alto)
    fuertes = [z for z in fis_all if z["total"] >= 9 and z["neto_pct"] >= 40]
    if modo == "fisico":
        return _marcar_canibalizacion(fuertes)
    # delivery se evalua con SU PROPIA logica (contra cocinas reales), sin asumir
    # nada de puntos fisicos potenciales. Solo evitamos repetir los fisicos fuertes.
    _fis_pts = [(z["lat"], z["lon"]) for z in fuertes]
    from . import nacional
    from .demand import vetoed
    c = nacional.CIUDADES[cid]; bb = c["bbox"]
    kk = nacional.kitchens_ciudad(cid)
    step = 0.012  # ~1.3 km
    cand = []
    la = bb[0]
    while la <= bb[2]:
        lo = bb[1]
        while lo <= bb[3]:
            from .censo import census_at as _cat
            dem = nacional.order_demand_at(la, lo, cid)
            _c = _cat(la, lo); pobn = min(1.0, _c["pob"]/8000.0)
            ftsig = max(dem, pobn)
            cov = nacional.coverage_at(la, lo, kk)
            veto = vetoed(la, lo) and modo != "fisico"   # en punto fisico el veto NO aplica
            if modo == "fisico":
                # storefront: nivel ALTO (nse fino) y que NO haya cocina propia
                # dentro de la zona (<2.5 km = ya es tu turf, ej. Coapa).
                mind = min((haversine_km(la, lo, k["lat"], k["lon"]) for k in kk),
                           default=99)
                ok = (_c["nse"] >= 0.80) and (mind > 2.5)
            else:
                ok = (ftsig >= 0.35) and (cov < 0.25) and not veto
            if ok:
                s = scores12_nal(la, lo, cid, kk, modo)
                cand.append({"lat": round(la,5), "lon": round(lo,5), "s": s})
            lo += step
        la += step
    cand.sort(key=lambda r: r["s"]["rank"], reverse=True)
    # fusion: en delivery los puntos se canibalizan a 4 km; en punto fisico
    # (storefront, tráfico de pie) basta 2.5 km para considerarlos distintos.
    merge_km = 2.5 if modo == "fisico" else 4.0
    zones = []
    for r in cand:
        if any(haversine_km(r["lat"], r["lon"], z["lat"], z["lon"]) < merge_km for z in zones):
            continue
        zones.append(r)
    out = []
    for z in zones:
        s = z["s"]; nombre = _nombre_hueco_nal(z["lat"], z["lon"])
        marca, why = recommend_marca({"marca_hint": _marca_hint_at(z["lat"], z["lon"]),
                                      "comercial_activity": s["dem"],
                                      "ingreso_premium": s["nse"]}, cfg)
        out.append({"lat": z["lat"], "lon": z["lon"], "nombre": nombre,
                    "total": s["total"], "ft": s["ft"], "pop": s["pop"],
                    "comp": s["comp"], "canib": s["canib"], "hub": s["hub"],
                    "pob": s["pob"], "nse": s["nse"], "cobertura": s["cov"],
                    "neto_pct": net_uncovered_pct_nal(z["lat"], z["lon"], kk),
                    "competidores": s["competidores"],
                    "marca_sugerida": marca, "porque": why})
    # umbral segun modo
    if modo == "fisico":
        out = [z for z in out if z["total"] >= 9 and z["neto_pct"] >= 45]
    else:
        out = [z for z in out if z["total"] >= 9 and z["neto_pct"] >= 50]
        # no repetir: excluir SOLO las que ya son buen PUNTO FISICO (score alto)
        out = [z for z in out
               if not any(haversine_km(z["lat"], z["lon"], fl, fo) < 2.5
                          for fl, fo in _fis_pts)]
    # dedup por nombre
    seen, ded = set(), []
    for z in sorted(out, key=lambda x: (x["total"], x["neto_pct"]), reverse=True):
        if z["nombre"] in seen: continue
        seen.add(z["nombre"]); ded.append(z)
    ded = _marcar_canibalizacion(ded)
    return ded

def _marca_hint_at(lat, lon):
    from .demand import _ANCHORS
    best, bd = None, 1.8
    for a in _ANCHORS:
        d = haversine_km(lat, lon, a["lat"], a["lon"])
        if d < bd: bd, best = d, a.get("marca")
    return best

def net_uncovered_pct_nal(lat, lon, city_kitchens, radius_km=4.0, n=200):
    from . import nacional
    import random
    unc = 0
    for _ in range(n):
        ang = random.random()*2*math.pi; rr = radius_km*math.sqrt(random.random())
        dlat = rr/111.0*math.cos(ang); dlon = rr/(111.0*math.cos(math.radians(lat)))*math.sin(ang)
        if nacional.coverage_at(lat+dlat, lon+dlon, city_kitchens) < 0.2: unc += 1
    return round(100*unc/n)

# Radar de locales — Foodology

Barre todo CDMX, cruza tu red actual contra la demanda de cada zona (empleo,
negocios y población), detecta **todos los huecos de cobertura** y te deja
**pegar locales** para rankearlos con un score 0–100. Todo en una página web
que abres desde el iPad.

---

## Cómo funciona (en corto)
- **Huecos:** demanda de la zona × (1 − cobertura de tu red). Alta demanda + poca
  presencia tuya = hueco. Se penaliza fuerte lo que canibaliza tus puntos.
- **Marca sugerida por zona:** Avocalia (premium/concurrida), Green House
  (media/oficinas), Dark kitchen (barata/no comercial, buena para reparto).
- **Score de un local:** m²/renta 20 · calidad de zona 30 · cobertura del hueco 30
  · competencia 10 · adecuaciones 10. Filtros que descartan: 80–200 m²,
  ≤ $1,200/m², gas y extracción obligatorios.

## Dos modos
- **Modo muestra:** sin llaves, corre con datos sintéticos. Sirve para ver la
  interfaz. Los números NO son reales.
- **Modo en vivo:** con tus llaves de Google e INEGI (en Render), usa datos
  reales de la ciudad.

---

## Subirlo a Render (sin línea de comandos)

**1. Poner el código en GitHub (desde el navegador):**
- Entra a github.com → *New repository* → nómbralo `foodology-site-radar` → *Create*.
- En el repo: *Add file → Upload files* → arrastra **todos** estos archivos y
  carpetas → *Commit changes*.

**2. Conectar Render:**
- Entra a render.com (cuenta gratis) → *New → Web Service* → conecta tu GitHub y
  elige el repo. Render detecta `render.yaml` solo.

**3. Pegar las llaves (aquí van, por fin):**
- En el servicio → pestaña *Environment* → *Add Environment Variable*:
  - `GOOGLE_MAPS_API_KEY` = tu llave de Google
  - `INEGI_TOKEN` = tu token de INEGI
- *Save changes.* (Nunca van en el código ni en el chat.)

**4. Abrir:** Render te da una URL tipo `https://foodology-site-radar.onrender.com`.
Ábrela desde el iPad. Esa es tu página.

**5. Cada lunes (opcional, automático):** en Render → *New → Cron Job* →
schedule `0 9 * * 1` (lunes 9am) → comando
`curl -X POST https://TU-URL.onrender.com/api/refresh`. Refresca los huecos con
datos nuevos.

---

## Correrlo en tu laptop (opcional, para probar)
1. Copia `.env.example` a `.env` y pega tus dos llaves.
2. `pip install -r requirements.txt`
3. `python app.py` → abre `http://localhost:5000`

## Cambiar parámetros
Todo lo editable está en **`config.yaml`** (rangos de m², renta, pesos del score,
radios de canibalización, mezcla de demanda). No toques el código.

## Datos de tu red
Están en `data/red_actual.csv` (19 puntos propios + 2 prospectos). Edita ese
archivo para agregar o quitar puntos.

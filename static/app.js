const NET = window.__NET__, GAPS = window.__GAPS__, CFG = window.__CFG__;
const cls = s => (s||"").replace(/ /g,".");

const map = L.map("map",{zoomControl:true}).setView([19.41,-99.16],11);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{
  attribution:"© OpenStreetMap © CARTO", subdomains:"abcd", maxZoom:19}).addTo(map);

// ---- red propia ----
const ringLayer = L.layerGroup();
NET.forEach(p=>{
  const r=(p.radio_km || 3.0)*1000;   // radio real de cobertura del punto
  L.circle([p.lat,p.lon],{radius:r,color:"#35C2B1",weight:1,opacity:.3,
    fillColor:"#35C2B1",fillOpacity:.06}).addTo(ringLayer);
  L.circleMarker([p.lat,p.lon],{radius:5,color:"#0E141B",weight:1.5,
    fillColor:"#35C2B1",fillOpacity:1}).addTo(map)
   .bindPopup(`<b>${p.nombre}</b><br>${p.marca} · ${p.tipo}<br>cobertura ${p.radio_km} km · <i>${p.estatus}</i>`);
});
document.getElementById("ringsTgl").addEventListener("change",e=>{
  e.target.checked?ringLayer.addTo(map):map.removeLayer(ringLayer);
});
document.getElementById("netCount").textContent = NET.length+" puntos propios";

// ---- huecos ----
const gapMarkers={};
GAPS.forEach((g,i)=>{
  const rad = 8 + g.gap*26;
  const m=L.circleMarker([g.lat,g.lon],{radius:rad,color:"#F2A63B",weight:1.5,
    fillColor:"#F2A63B",fillOpacity:.28})
    .addTo(map)
    .bindPopup(`<b>#${i+1} · ${g.nombre||"hueco"}</b><br>`+
      `demanda ${g.demanda} · cobertura ${g.cobertura}<br>`+
      `<b>Sugerido: ${g.marca_sugerida}</b><br><span style="color:#8695A6">${g.porque}</span>`);
  gapMarkers[i]=m;
});

const gl=document.getElementById("gapList");
GAPS.forEach((g,i)=>{
  const li=document.createElement("li");
  li.innerHTML=`<span class="rank">${String(i+1).padStart(2,"0")}</span>
    <div><div class="gname">${g.nombre||"Hueco "+(i+1)}</div>
    <div class="gwhy"><span class="chip ${cls(g.marca_sugerida)}">${g.marca_sugerida}</span></div></div>
    <span class="gscore">${g.gap.toFixed(2)}</span>`;
  li.addEventListener("click",()=>{map.setView([g.lat,g.lon],14);gapMarkers[i].openPopup();});
  gl.appendChild(li);
});

// ---- scoring de locales ----
const locMarkers=L.layerGroup().addTo(map);
const btn=document.getElementById("scoreBtn");
btn.addEventListener("click",async()=>{
  const txt=document.getElementById("locInput").value;
  if(!txt.trim())return;
  btn.disabled=true;btn.textContent="Evaluando…";
  try{
    const r=await fetch("/api/score",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({locales:txt})});
    const data=await r.json();
    renderResults(data.results);
  }catch(e){document.getElementById("results").innerHTML=
    `<div class="rcard descartado"><div class="addr">Error de conexion. Reintenta.</div></div>`;}
  btn.disabled=false;btn.textContent="Evaluar y rankear";
});

function bar(label,v){return `<div class="bar"><span>${label}</span>
  <div class="track"><div class="fill" style="width:${Math.round(v*100)}%"></div></div></div>`;}

function renderResults(res){
  locMarkers.clearLayers();
  const box=document.getElementById("results");box.innerHTML="";
  res.forEach(x=>{
    const card=document.createElement("div");card.className="rcard "+x.estado;
    let head = x.score!=null ? `<span class="big">${x.score}</span>`
             : `<span class="big">${x.estado.replace("_"," ")}</span>`;
    let comp="", notes="";
    if(x.componentes){const c=x.componentes;
      comp=`<div class="bars">${bar("m2/renta",c.m2_renta)}${bar("zona",c.zona)}
        ${bar("hueco",c.hueco)}${bar("competencia",c.competencia)}${bar("adecuaciones",c.adecuaciones)}</div>`;}
    if(x.marca_sugerida) notes+=`<div class="notes"><span class="chip ${cls(x.marca_sugerida)}">${x.marca_sugerida}</span> ${x.porque_marca||""}</div>`;
    (x.descartes||[]).forEach(d=>notes+=`<div class="notes bad">✕ ${d}</div>`);
    (x.motivos||[]).forEach(m=>notes+=`<div class="notes">· ${m}</div>`);
    card.innerHTML=`<div class="top"><div class="addr">${x.direccion}</div>${head}</div>${comp}${notes}`;
    box.appendChild(card);
    if(x.lat){
      const col = x.estado==="candidato" ? "#35C2B1" : "#E4572E";
      L.circleMarker([x.lat,x.lon],{radius:7,color:"#fff",weight:2,
        fillColor:col,fillOpacity:1}).addTo(locMarkers)
        .bindPopup(`<b>${x.direccion}</b><br>score ${x.score??"—"}`);
    }
  });
  if(res.some(x=>x.lat)) box.scrollIntoView({behavior:"smooth"});
}

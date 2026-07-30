const CITIES = window.__CITIES__, CFG = window.__CFG__;
let CITY = window.__CITY__;
const cls = s => (s||"").replace(/ /g,".");
const pill = (lbl,v)=>`<span class="s12"><b>${v}</b>${lbl}</span>`;
const breakdown = g => pill("FT",g.ft)+pill("Nivel",g.pop)+pill("Rest",g.comp)+pill("NoCan",g.canib);

const map = L.map("map",{zoomControl:true}).setView(CITY.centro, CITY.zoom);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",{
  attribution:"© OpenStreetMap © CARTO", subdomains:"abcd", maxZoom:19}).addTo(map);

const netLayer = L.layerGroup().addTo(map);   // marcadores cocinas
const ringLayer = L.layerGroup();             // coberturas (toggle)
const gapLayer = L.layerGroup().addTo(map);   // huecos
const locMarkers = L.layerGroup().addTo(map); // locales evaluados
let ringsOn = false;

// selector de ciudad
const sel = document.getElementById("citySel");
CITIES.forEach(c=>{
  const o=document.createElement("option"); o.value=c.id; o.textContent=c.nombre;
  if(c.id===CITY.id) o.selected=true; sel.appendChild(o);
});
sel.addEventListener("change", async e=>{
  sel.disabled=true;
  await loadCityData(e.target.value, true);
  sel.disabled=false;
});

function renderCity(){
  netLayer.clearLayers(); ringLayer.clearLayers(); gapLayer.clearLayers(); locMarkers.clearLayers();

  // red propia
  CITY.network.forEach(p=>{
    const r=(p.radio_km||3.0)*1000;
    L.circle([p.lat,p.lon],{radius:r,color:"#35C2B1",weight:1,opacity:.3,
      fillColor:"#35C2B1",fillOpacity:.06}).addTo(ringLayer);
    L.circleMarker([p.lat,p.lon],{radius:5,color:"#0E141B",weight:1.5,
      fillColor:"#35C2B1",fillOpacity:1}).addTo(netLayer)
     .bindPopup(`<b>${p.nombre}</b><br>cocina · cobertura ${p.radio_km} km`);
  });
  document.getElementById("netCount").textContent = CITY.network.length+" cocinas · "+CITY.gaps.length+" huecos";
  document.getElementById("gapSub").textContent = CITY.nombre+" · "+CITY.gaps.length+" huecos por score /12"+(CITY.nivel?"":" · (sin Nivel aún)");

  // huecos
  const gl=document.getElementById("gapList"); gl.innerHTML="";
  const gapMarkers={};
  CITY.gaps.forEach((g,i)=>{
    L.circle([g.lat,g.lon],{radius:3000,color:"#F2A63B",weight:1.5,opacity:.9,
      fillColor:"#F2A63B",fillOpacity:.12}).addTo(gapLayer);
    const comp=(g.competidores&&g.competidores.length)?g.competidores.join(", "):"ninguno cerca";
    const turbo=g.hub?'<br><span class="turbo">⚡ aquí puedes prender Turbo</span>':"";
    const m=L.circleMarker([g.lat,g.lon],{radius:6,color:"#1A1206",weight:1.5,
      fillColor:"#F2A63B",fillOpacity:1}).addTo(gapLayer)
      .bindPopup(`<b>#${i+1} · ${g.nombre}</b> — <b>${g.total}/12</b><br>`+
        `FT ${g.ft} · Nivel ${g.pop} · Rest.parecidos ${g.comp} · NoCanib ${g.canib}<br>`+
        `población ~${(g.pob||0).toLocaleString()} · cobertura ${g.cobertura} · <b>hueco neto ${g.neto_pct}%</b><br>`+
        `restaurantes parecidos: ${comp}${turbo}<br><b>Sugerido: ${g.marca_sugerida}</b>`);
    m.bindTooltip(`${g.total}`,{permanent:true,direction:"center",className:"gap-num"});
    gapMarkers[i]=m;

    const li=document.createElement("li");
    li.innerHTML=`<span class="rank">${String(i+1).padStart(2,"0")}</span>
      <div><div class="gname">${g.nombre} ${g.hub?'<span class="turbo-tag">⚡Turbo</span>':''}</div>
      <div class="gwhy"><span class="chip ${cls(g.marca_sugerida)}">${g.marca_sugerida}</span> ${breakdown(g)}</div>
      <div class="gnet">hueco neto ${g.neto_pct}% · pob ~${(g.pob||0).toLocaleString()}</div></div>
      <span class="gscore">${g.total}<small>/12</small></span>`;
    li.addEventListener("click",()=>{map.setView([g.lat,g.lon],14);gapMarkers[i].openPopup();});
    gl.appendChild(li);
  });
  if(ringsOn) ringLayer.addTo(map);
}

document.getElementById("ringsTgl").addEventListener("change",e=>{
  ringsOn=e.target.checked;
  ringsOn?ringLayer.addTo(map):map.removeLayer(ringLayer);
});

// ---- evaluar locales ----
const btn=document.getElementById("scoreBtn");
btn.addEventListener("click",async()=>{
  const txt=document.getElementById("locInput").value;
  if(!txt.trim())return;
  btn.disabled=true;btn.textContent="Evaluando…";
  try{
    const r=await fetch("/api/score",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({locales:txt})});
    renderResults((await r.json()).results);
  }catch(e){document.getElementById("results").innerHTML=
    `<div class="rcard descartado"><div class="addr">Error de conexión. Reintenta.</div></div>`;}
  btn.disabled=false;btn.textContent="Evaluar y rankear";
});

function renderResults(res){
  locMarkers.clearLayers();
  const box=document.getElementById("results");box.innerHTML="";
  res.forEach(x=>{
    const card=document.createElement("div");card.className="rcard "+x.estado;
    let head=x.score!=null?`<span class="big">${x.score}<small>/12</small></span>`:`<span class="big">${x.estado.replace("_"," ")}</span>`;
    let comp="",notes="";
    if(x.componentes){const c=x.componentes;
      comp=`<div class="gwhy" style="margin-top:6px">${pill("FT",c.ft)}${pill("Nivel",c.pop)}${pill("Rest",c.comp)}${pill("NoCan",c.canib)}</div>`;}
    if(x.marca_sugerida) notes+=`<div class="notes"><span class="chip ${cls(x.marca_sugerida)}">${x.marca_sugerida}</span> ${x.porque_marca||""}</div>`;
    if(x.estado==="candidato"){
      notes+=`<div class="notes">${x.ciudad||""} · población ~${(x.pob||0).toLocaleString()} · hueco neto ${x.neto_pct}%${x.hub?' · <span class="turbo">⚡Turbo</span>':''}</div>`;
      notes+=`<div class="notes">restaurantes parecidos: ${(x.competidores&&x.competidores.length)?x.competidores.join(", "):"ninguno cerca"}</div>`;
    }
    (x.descartes||[]).forEach(d=>notes+=`<div class="notes bad">✕ ${d}</div>`);
    (x.motivos||[]).forEach(m=>notes+=`<div class="notes">· ${m}</div>`);
    card.innerHTML=`<div class="top"><div class="addr">${x.direccion}</div>${head}</div>${comp}${notes}`;
    box.appendChild(card);
    if(x.lat){const col=x.estado==="candidato"?"#35C2B1":"#E4572E";
      L.circleMarker([x.lat,x.lon],{radius:7,color:"#fff",weight:2,fillColor:col,fillOpacity:1})
        .addTo(locMarkers).bindPopup(`<b>${x.direccion}</b><br>${x.score!=null?x.score+"/12":"descartado"}`);}
  });
  if(res.some(x=>x.lat)) box.scrollIntoView({behavior:"smooth"});
}

renderCity();                 // pinta red al instante
loadCityData(CITY.id, false); // trae los huecos en segundo plano

async function loadCityData(cid, recenter){
  const sub=document.getElementById("gapSub");
  sub.textContent="calculando huecos…";
  try{
    const r=await fetch("/api/ciudad/"+cid);
    CITY=await r.json(); renderCity();
    if(recenter) map.setView(CITY.centro, CITY.zoom);
  }catch(err){ sub.textContent="No pude calcular los huecos. Recarga."; }
}

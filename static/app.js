const CITIES = window.__CITIES__, CFG = window.__CFG__;
let CITY = window.__CITY__;
let MODO = 'fisico';
const cls = s => (s||"").replace(/ /g,".");
const pill = (lbl,v)=>`<span class="s12"><b>${v}</b>${lbl}</span>`;
const colorVal = v => v==="alto"?"#35C2B1":(v==="medio"?"#F2A63B":"#8695A6");
const breakdown = g => (g.explica||[]).map(e=>
  `<div class="exp"><span class="expv" style="color:${colorVal(e.valor)}">${e.valor.toUpperCase()} (${e.n}/3)</span> <b>${e.label}</b> — ${e.frase}</div>`).join("");

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
  if(MODO==="plan") mostrarPlanUI();
  sel.disabled=false;
});

function renderCity(){
  netLayer.clearLayers(); ringLayer.clearLayers(); gapLayer.clearLayers(); locMarkers.clearLayers();

  // red propia
  CITY.network.forEach(p=>{
    const r=(p.radio_km||3.0)*1000;
    const kpop=`<b>🍳 ${p.nombre}</b><br>Cocina activa · cobertura ${p.radio_km} km`;
    L.circle([p.lat,p.lon],{radius:r,color:"#35C2B1",weight:1,opacity:.3,
      fillColor:"#35C2B1",fillOpacity:.06}).addTo(ringLayer).bindPopup(kpop);
    L.circleMarker([p.lat,p.lon],{radius:6,color:"#0E141B",weight:1.5,
      fillColor:"#35C2B1",fillOpacity:1}).addTo(netLayer).bindPopup(kpop);
  });
  document.getElementById("netCount").textContent = CITY.network.length+" cocinas · "+CITY.gaps.length+" huecos";
  const modoTxt = (MODO==="fisico") ? "PUNTO FÍSICO" : "DELIVERY / DARK KITCHEN";
  document.getElementById("gapSub").innerHTML = "<b>"+modoTxt+"</b> · "+CITY.nombre+" · "+CITY.gaps.length+" zonas";

  // huecos
  const gl=document.getElementById("gapList"); gl.innerHTML="";
  const gapMarkers={};
  CITY.gaps.forEach((g,i)=>{
    const comp=(g.competidores&&g.competidores.length)?g.competidores.join(", "):"ninguno cerca";
    const turbo=g.hub?'<br><span class="turbo">⚡ aquí puedes prender Turbo</span>':"";
    const expTxt=(g.explica||[]).map(e=>`${e.label}: <b>${e.valor.toUpperCase()} (${e.n}/3)</b>`).join("<br>");
    const gpop=`<b>#${i+1} · ${g.nombre}</b> — <b>${g.total}/12</b><br>`+
        (g.marca_sugerida?`<span class="chip ${cls(g.marca_sugerida)}">${g.marca_sugerida}</span><br>`:"")+
        expTxt+`<br>`+
        `hueco neto <b>${g.neto_pct}%</b> · pob ~${(g.pob||0).toLocaleString()}${turbo}`+
        ((g.alternativas&&g.alternativas.length)?`<br><span style="color:#F2C94C">⚄ Compite con: ${g.alternativas.join(", ")} (elige una)</span>`:"");
    // circulo grande CON popup (para que al clic en cualquier parte diga que es)
    L.circle([g.lat,g.lon],{radius:3000,color:"#F2A63B",weight:1.5,opacity:.9,
      fillColor:"#F2A63B",fillOpacity:.12}).addTo(gapLayer).bindPopup(gpop);
    const m=L.circleMarker([g.lat,g.lon],{radius:7,color:"#1A1206",weight:1.5,
      fillColor:"#F2A63B",fillOpacity:1}).addTo(gapLayer).bindPopup(gpop);
    m.bindTooltip(`${i+1}`,{permanent:true,direction:"center",className:"gap-num"});
    gapMarkers[i]=m;

    const altTxt = (g.alternativas && g.alternativas.length)
      ? `<div class="alt">⚄ Compite con <b>${g.alternativas.join(", ")}</b> — abre solo UNA de estas</div>` : "";
    const grpTag = g.grupo ? `<span class="grp grp-${g.grupo%6}">⚄ grupo ${g.grupo}</span>` : "";
    const li=document.createElement("li");
    li.innerHTML=`
      <div class="ghead">
        <span class="rank">${String(i+1).padStart(2,"0")}</span>
        <div class="gtitle"><span class="gname">${g.nombre}</span> ${grpTag} ${g.hub?'<span class="turbo-tag">⚡Turbo</span>':''}
          ${g.marca_sugerida?`<span class="chip ${cls(g.marca_sugerida)}">${g.marca_sugerida}</span>`:""}</div>
        <span class="gscore">${g.total}<small>/12</small></span>
        <span class="chev">▸</span>
      </div>
      <div class="gdetail">
        ${breakdown(g)}
        <div class="gnet">hueco neto ${g.neto_pct}% · pob ~${(g.pob||0).toLocaleString()}</div>${altTxt}
        <div class="gmapbtn">Ver en el mapa →</div>
      </div>`;
    // clic en el encabezado: expandir/colapsar el detalle
    const head=li.querySelector(".ghead");
    head.addEventListener("click",()=>{
      li.classList.toggle("open");
    });
    // clic en "ver en el mapa"
    li.querySelector(".gmapbtn").addEventListener("click",(e)=>{
      e.stopPropagation(); map.setView([g.lat,g.lon],14); gapMarkers[i].openPopup();
    });
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

// switch de modo
document.querySelectorAll("#modoSwitch button").forEach(b=>{
  b.addEventListener("click", async ()=>{
    if(b.classList.contains("on")) return;
    document.querySelectorAll("#modoSwitch button").forEach(x=>x.classList.remove("on"));
    b.classList.add("on"); MODO=b.dataset.modo;
    if(MODO==="plan"){ mostrarPlanUI(); }
    else { document.getElementById("planResult").innerHTML=""; await loadCityData(CITY.id, false); }
  });
});

function mostrarPlanUI(){
  document.getElementById("gapList").innerHTML="";
  document.getElementById("gapSub").innerHTML="<b>PLAN DE EXPANSIÓN</b> · "+CITY.nombre+" · elige cuántas cocinas";
  const box=document.getElementById("planResult");
  box.innerHTML=`<div class="plan-box">
    <span class="plan-lbl">¿Cuántas cocinas vas a abrir?</span>
    <button class="plan-btn" data-n="2">2</button>
    <button class="plan-btn" data-n="3">3</button>
    <button class="plan-btn" data-n="5">5</button>
    <button class="plan-btn" data-n="8">8</button>
  </div>
  <div class="plan-base">¿Punto físico o delivery?
    <button class="plan-base-btn on" data-base="fisico">Físico</button>
    <button class="plan-base-btn" data-base="delivery">Delivery</button></div>
  <div id="planInner"></div>`;
  gapLayer.clearLayers();
  let baseModo="fisico";
  box.querySelectorAll(".plan-base-btn").forEach(bb=>bb.addEventListener("click",()=>{
    box.querySelectorAll(".plan-base-btn").forEach(x=>x.classList.remove("on"));
    bb.classList.add("on"); baseModo=bb.dataset.base;
  }));
  box.querySelectorAll(".plan-btn").forEach(b=>b.addEventListener("click", async ()=>{
    box.querySelectorAll(".plan-btn").forEach(x=>x.classList.remove("on")); b.classList.add("on");
    document.getElementById("planInner").innerHTML='<div class="plan-load">calculando el mejor plan…</div>';
    try{
      const r=await fetch("/api/plan/"+CITY.id+"?modo="+baseModo+"&n="+b.dataset.n);
      renderPlan((await r.json()).plan);
    }catch(e){ document.getElementById("planInner").innerHTML='<div class="plan-load">error, reintenta</div>'; }
  }));
}
// plan de cobertura
document.querySelectorAll(".plan-btn").forEach(b=>{
  b.addEventListener("click", async ()=>{
    const n=b.dataset.n;
    document.querySelectorAll(".plan-btn").forEach(x=>x.classList.remove("on"));
    b.classList.add("on");
    const box=document.getElementById("planResult");
    box.innerHTML='<div class="plan-load">calculando el mejor plan de '+n+' aperturas…</div>';
    try{
      const r=await fetch("/api/plan/"+CITY.id+"?modo="+MODO+"&n="+n);
      const data=await r.json();
      renderPlan(data.plan);
    }catch(e){ box.innerHTML='<div class="plan-load">error, reintenta</div>'; }
  });
});
document.getElementById("planClear").addEventListener("click", ()=>{
  document.getElementById("planResult").innerHTML="";
  document.getElementById("planClear").style.display="none";
  document.querySelectorAll(".plan-btn").forEach(x=>x.classList.remove("on"));
  renderCity();
});

function renderPlan(plan){
  const box=document.getElementById("planInner");
  gapLayer.clearLayers();
  let html='<div class="plan-title">Plan óptimo — cubre '+(plan[plan.length-1]?.pob_acumulada||0).toLocaleString()+' personas</div>';
  plan.forEach((z,i)=>{
    // marcar en el mapa con numero de orden
    L.circle([z.lat,z.lon],{radius:4000,color:"#35C2B1",weight:2,opacity:.9,fillColor:"#35C2B1",fillOpacity:.10}).addTo(gapLayer);
    L.circleMarker([z.lat,z.lon],{radius:11,color:"#0E141B",weight:2,fillColor:"#35C2B1",fillOpacity:1}).addTo(gapLayer)
      .bindTooltip(`${z.orden_plan}`,{permanent:true,direction:"center",className:"plan-num"})
      .bindPopup(`<b>#${z.orden_plan} · ${z.nombre}</b><br>${z.total}/12 · pob ~${(z.pob||0).toLocaleString()}<br>acumulado: ${(z.pob_acumulada||0).toLocaleString()} personas`);
    html+=`<div class="plan-row"><span class="plan-ord">${z.orden_plan}</span>
      <div><b>${z.nombre}</b> <span class="chip ${cls(z.marca_sugerida)}">${z.marca_sugerida}</span>
      <div class="plan-sub">${z.total}/12 · +${(z.pob||0).toLocaleString()} personas · acumulado ${(z.pob_acumulada||0).toLocaleString()}</div></div></div>`;
  });
  box.innerHTML=html;
  if(plan.length){ const b=L.latLngBounds(plan.map(z=>[z.lat,z.lon])); map.fitBounds(b,{padding:[60,60],maxZoom:13}); }
}
renderCity();                 // pinta red al instante
loadCityData(CITY.id, false); // trae los huecos en segundo plano

async function loadCityData(cid, recenter){
  const sub=document.getElementById("gapSub");
  sub.textContent="calculando huecos…";
  try{
    const r=await fetch("/api/ciudad/"+cid+"?modo="+MODO);
    CITY=await r.json(); renderCity();
    if(recenter) map.setView(CITY.centro, CITY.zoom);
  }catch(err){ sub.textContent="No pude calcular los huecos. Recarga."; }
}

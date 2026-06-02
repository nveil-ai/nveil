// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

/* Visuals Animation */
export function init() {

const __rootEl = document.getElementById('vs-stage');
if (!__rootEl) return;
const __alive = () => __rootEl && document.body.contains(__rootEl);
const __origSetTimeout = window.setTimeout.bind(window);
const __origSetInterval = window.setInterval.bind(window);
const __origClearInterval = window.clearInterval.bind(window);
function setTimeout(fn, ms) {
  return __origSetTimeout(() => { if (__alive()) fn(); }, ms);
}
function setInterval(fn, ms) {
  let id;
  id = __origSetInterval(() => {
    if (!__alive()) { __origClearInterval(id); return; }
    fn();
  }, ms);
  return id;
}
function clearTimeout(id) { return window.clearTimeout(id); }
function clearInterval(id) { return __origClearInterval(id); }

const SERIES = [
  { id:'revenue', label:'Revenue',  color:'#9662FE', values:[45,62,55,80,72,98,88,115,105,130,118,145] },
  { id:'target',  label:'Target',   color:'#C49BFF', values:[50,55,60,65,70,75,80,85,90,95,100,105], dash:true },
  { id:'cost',    label:'Cost',     color:'#FF6B9D', values:[30,35,32,42,40,52,48,58,55,65,62,70] },
];
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const W = 664, H = 210;

let sceneTimer  = null;
let visibleSeries = new Set(['revenue','target','cost']);
let zoomLevel = 1;
let zoomRange = { start:0, end:11 };

const svg       = document.getElementById('vs-mainSvg');
const tooltip   = document.getElementById('vs-tooltip');
const ttTitle   = document.getElementById('vs-ttTitle');
const ttRows    = document.getElementById('vs-ttRows');
const chartLbl  = document.getElementById('vs-chartLabel');
const toolbar   = document.getElementById('vs-toolbar');
const exportBtn = document.getElementById('vs-exportBtn');
const exportDD  = document.getElementById('vs-exportDropdown');
const zoomBadge = document.getElementById('vs-zoomBadge');
const cursor    = document.getElementById('vs-cursor');
const dotsEl    = document.getElementById('vs-dots');

const SCENES = 4;
dotsEl.innerHTML = '';
for(let i=0;i<SCENES;i++){
  const d=document.createElement('div');
  d.className='dot'; d.id=`vs-dot-${i}`; dotsEl.appendChild(d);
}
function setDot(i){ for(let j=0;j<SCENES;j++){ const el=document.getElementById(`vs-dot-${j}`); if(el) el.className='dot'+(j===i?' active':''); } }

function scale(val,min,max,outMin,outMax){ return outMin+(val-min)/(max-min)*(outMax-outMin); }

function getPoints(series, range={start:0,end:11}) {
  const vals = series.values.slice(range.start, range.end+1);
  const allVals = SERIES.flatMap(s=>s.values.slice(range.start,range.end+1));
  const minV=Math.min(...allVals)*0.85, maxV=Math.max(...allVals)*1.08;
  const step = W/(vals.length-1);
  return vals.map((v,i)=>({
    x: i*step,
    y: H - scale(v,minV,maxV,8,H-8)
  }));
}

function buildPath(pts){ return pts.map((p,i)=>`${i===0?'M':'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '); }

function renderChart(animateIn=true) {
  svg.innerHTML='';
  const range = zoomRange;
  const months = MONTHS.slice(range.start, range.end+1);
  const step = W/(months.length-1);

  const defs = document.createElementNS('http://www.w3.org/2000/svg','defs');
  SERIES.forEach(s=>{
    const grad = document.createElementNS('http://www.w3.org/2000/svg','linearGradient');
    grad.setAttribute('id',`grad-${s.id}`);
    grad.setAttribute('x1','0'); grad.setAttribute('y1','0');
    grad.setAttribute('x2','0'); grad.setAttribute('y2','1');
    grad.innerHTML=`<stop offset="0%" stop-color="${s.color}" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="${s.color}" stop-opacity="0.01"/>`;
    defs.appendChild(grad);
  });
  svg.appendChild(defs);

  months.forEach((m,i)=>{
    const t=document.createElementNS('http://www.w3.org/2000/svg','text');
    t.setAttribute('x', (i*step).toFixed(1));
    t.setAttribute('y', H+2);
    t.setAttribute('text-anchor','middle');
    t.setAttribute('font-size','9');
    t.setAttribute('fill','#6B4F6B');
    t.setAttribute('font-family','Inter,sans-serif');
    t.textContent=m;
    svg.appendChild(t);
  });

  SERIES.forEach(s=>{
    if(!visibleSeries.has(s.id)) return;
    const pts = getPoints(s, range);
    const pathD = buildPath(pts);
    const totalLen = pts.reduce((acc,p,i)=>i===0?0:acc+Math.hypot(p.x-pts[i-1].x,p.y-pts[i-1].y),0);

    const areaD = `${pathD} L${pts[pts.length-1].x},${H} L${pts[0].x},${H} Z`;
    const area = document.createElementNS('http://www.w3.org/2000/svg','path');
    area.setAttribute('d', areaD);
    area.setAttribute('fill', `url(#grad-${s.id})`);
    area.style.opacity='0';
    svg.appendChild(area);

    const line = document.createElementNS('http://www.w3.org/2000/svg','path');
    line.setAttribute('d', pathD);
    line.setAttribute('fill','none');
    line.setAttribute('stroke', s.color);
    line.setAttribute('stroke-width', s.dash?'1.5':'2.2');
    line.setAttribute('stroke-linecap','round');
    line.setAttribute('stroke-linejoin','round');
    if(s.dash) line.setAttribute('stroke-dasharray','5 4');
    if(animateIn){
      line.style.strokeDasharray=totalLen;
      line.style.strokeDashoffset=totalLen;
      line.style.transition=`stroke-dashoffset 1.4s cubic-bezier(.4,0,.2,1)`;
      setTimeout(()=>{ line.style.strokeDashoffset=0; area.style.transition='opacity .8s .8s'; area.style.opacity=1; },60);
    }
    svg.appendChild(line);

    pts.forEach((p,i)=>{
      const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
      c.setAttribute('cx',p.x); c.setAttribute('cy',p.y); c.setAttribute('r','3.5');
      c.setAttribute('fill',s.color); c.setAttribute('stroke','#211920'); c.setAttribute('stroke-width','1.8');
      c.style.opacity='0';
      c.style.transition=`opacity .3s ${.9+i*.06}s`;
      c.dataset.series=s.id; c.dataset.index=i;
      setTimeout(()=>c.style.opacity='1', animateIn?900+i*60:0);
      svg.appendChild(c);
    });
  });
}

function showTooltip(x,y,monthIdx){
  const absIdx=zoomRange.start+monthIdx;
  ttTitle.textContent=MONTHS[absIdx]+' 2025';
  ttRows.innerHTML='';
  SERIES.filter(s=>visibleSeries.has(s.id)).forEach(s=>{
    const row=document.createElement('div');
    row.className='tooltip-row';
    row.innerHTML=`<div class="tooltip-dot" style="background:${s.color}"></div>
      <span style="color:#9B7F9E;font-size:10px;">${s.label}</span>
      <span class="tooltip-val" style="color:${s.color}">€${s.values[absIdx]}k</span>`;
    ttRows.appendChild(row);
  });
  const ttX=Math.min(x-30, W-130);
  const ttY=Math.max(y-80, 4);
  tooltip.style.left=ttX+'px'; tooltip.style.top=ttY+'px';
  tooltip.classList.add('visible');
}
function hideTooltip(){ tooltip.classList.remove('visible'); }

function buildChips(){
  document.getElementById('vs-toolbar').querySelectorAll('.chip').forEach(c=>c.remove());
  const group=document.createElement('div');
  group.style.cssText='display:flex;gap:5px;';
  SERIES.forEach(s=>{
    const chip=document.createElement('div');
    const on=visibleSeries.has(s.id);
    chip.className='chip';
    chip.dataset.series=s.id;
    chip.style.cssText=`border-color:${on?s.color+'80':'rgba(150,98,254,0.15)'};background:${on?s.color+'18':'transparent'};color:${on?s.color:'#6B4F6B'};`;
    chip.innerHTML=`<div class="chip-dot" style="background:${on?s.color:'#6B4F6B'}"></div>${s.label}`;
    group.appendChild(chip);
  });
  toolbar.insertBefore(group, document.getElementById('vs-tbtnGroup'));
}

function moveCursor(x,y,delay=0){
  setTimeout(()=>{
    cursor.style.opacity='1';
    cursor.style.left=x+'px';
    cursor.style.top=y+'px';
  }, delay);
}
function hideCursor(delay=0){ setTimeout(()=>cursor.style.opacity='0',delay); }

function litBadge(id){ const el=document.getElementById(id); if(el) el.classList.add('lit'); }
function dimBadge(id){ const el=document.getElementById(id); if(el) el.classList.remove('lit'); }
function dimAllBadges(){ ['vs-fb1','vs-fb2','vs-fb3','vs-fb4'].forEach(dimBadge); }

function elPos(el){
  const sr=document.getElementById('vs-stage').getBoundingClientRect();
  const er=el.getBoundingClientRect();
  return { x:er.left-sr.left+er.width/2, y:er.top-sr.top+er.height/2 };
}

function scene1(){
  setDot(0); dimAllBadges();
  chartLbl.textContent='REVENUE BY PRODUCT';
  visibleSeries=new Set(['revenue','target','cost']);
  zoomRange={start:0,end:11}; zoomLevel=1;
  zoomBadge.style.opacity='0';
  exportDD.classList.remove('open');
  buildChips(); renderChart(true);
  litBadge('vs-fb4');

  const range=zoomRange;
  const hoverPoints=[6,7,8,9];
  hoverPoints.forEach((idx,ii)=>{
    const pts=getPoints(SERIES[0],range);
    const px=pts[idx].x+18;
    const py=pts[idx].y+14;

    const cbr=document.getElementById('vs-chartBody').getBoundingClientRect();
    const sr=document.getElementById('vs-stage').getBoundingClientRect();
    const stageX=cbr.left-sr.left+px;
    const stageY=cbr.top-sr.top+py;

    moveCursor(stageX,stageY, 1400+ii*700);
    setTimeout(()=>showTooltip(px,py,idx), 1700+ii*700);
    setTimeout(()=>hideTooltip(), 2300+ii*700);
  });
}

function scene2(){
  setDot(1); dimAllBadges();
  chartLbl.textContent='REVENUE BY PRODUCT';
  visibleSeries=new Set(['revenue','target','cost']);
  zoomRange={start:0,end:11}; zoomLevel=1;
  zoomBadge.style.opacity='0';
  exportDD.classList.remove('open');
  buildChips(); renderChart(false);
  litBadge('vs-fb2');

  const toggleSeq=[
    { id:'cost',    show:false, delay:900 },
    { id:'target',  show:false, delay:1900 },
    { id:'cost',    show:true,  delay:2900 },
    { id:'target',  show:true,  delay:3700 },
  ];

  toggleSeq.forEach(({id,show,delay})=>{
    setTimeout(()=>{
      const chip=document.getElementById('vs-toolbar').querySelector(`.chip[data-series="${id}"]`);
      if(!chip) return;
      const p=elPos(chip);
      moveCursor(p.x-8, p.y+6);
    }, delay-180);

    setTimeout(()=>{
      if(show) visibleSeries.add(id);
      else visibleSeries.delete(id);
      buildChips(); renderChart(false);
    }, delay);
  });
}

function scene3(){
  setDot(2); dimAllBadges();
  chartLbl.textContent='REVENUE BY PRODUCT';
  visibleSeries=new Set(['revenue','target','cost']);
  zoomRange={start:0,end:11}; zoomLevel=1;
  zoomBadge.style.opacity='0';
  exportDD.classList.remove('open');
  buildChips(); renderChart(true);
  litBadge('vs-fb1');

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnZoomIn');
    const p=elPos(btn);
    moveCursor(p.x-6,p.y+6);
  }, 1300);

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnZoomIn');
    btn.classList.add('clicked','active');
    setTimeout(()=>btn.classList.remove('clicked'),200);
    zoomRange={start:3,end:9}; zoomLevel=2;
    zoomBadge.style.opacity='1';
    zoomBadge.textContent='2×';
    renderChart(true);
  }, 1700);

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnZoomIn');
    const p=elPos(btn);
    moveCursor(p.x-6,p.y+6);
  }, 3000);

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnZoomIn');
    btn.classList.add('clicked','active');
    setTimeout(()=>btn.classList.remove('clicked'),200);
    zoomRange={start:5,end:8}; zoomLevel=3;
    zoomBadge.textContent='3×';
    renderChart(true);
  }, 3400);

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnReset');
    const p=elPos(btn);
    moveCursor(p.x-6,p.y+6);
  }, 4800);

  setTimeout(()=>{
    const btn=document.getElementById('vs-btnReset');
    btn.classList.add('clicked');
    setTimeout(()=>btn.classList.remove('clicked'),200);
    zoomRange={start:0,end:11}; zoomLevel=1;
    zoomBadge.style.opacity='0';
    document.getElementById('vs-btnZoomIn').classList.remove('active');
    renderChart(true);
  }, 5100);
}

function scene4(){
  setDot(3); dimAllBadges();
  chartLbl.textContent='REVENUE BY PRODUCT';
  visibleSeries=new Set(['revenue','target','cost']);
  zoomRange={start:0,end:11}; zoomLevel=1;
  zoomBadge.style.opacity='0';
  exportDD.classList.remove('open');
  buildChips(); renderChart(true);
  litBadge('vs-fb3');

  setTimeout(()=>{
    const p=elPos(exportBtn);
    moveCursor(p.x-6, p.y+6);
  }, 1200);

  setTimeout(()=>{
    exportBtn.classList.add('lit');
    exportDD.classList.add('open');
  }, 1600);

  setTimeout(()=>{
    const p=elPos(document.getElementById('vs-exp-csv'));
    moveCursor(p.x-80, p.y+6);
    document.getElementById('vs-exp-csv').classList.add('hovered');
  }, 2200);

  setTimeout(()=>{
    const p=elPos(document.getElementById('vs-exp-png'));
    moveCursor(p.x-80, p.y+6);
    document.getElementById('vs-exp-csv').classList.remove('hovered');
    document.getElementById('vs-exp-png').classList.add('hovered');
  }, 3000);

  setTimeout(()=>{
    exportDD.classList.remove('open');
    exportBtn.classList.remove('lit');
    document.getElementById('vs-exp-png').classList.remove('hovered');
    hideCursor();
  }, 4000);
}

const SCENE_FNS=[scene1,scene2,scene3,scene4];
const SCENE_DURATIONS=[5500,5500,6800,5500];

function runScene(i){
  hideCursor();
  hideTooltip();
  SCENE_FNS[i]();
  sceneTimer=setTimeout(()=>runScene((i+1)%SCENE_FNS.length), SCENE_DURATIONS[i]);
}

runScene(0);

}

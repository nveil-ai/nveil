// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

/* Describe Animation */
export function init() {

const __rootEl = document.getElementById('ds-chartArea');
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

const SCENES = [
  {
    lang: 'EN',
    prompt: 'Show me sales by region as a bar chart',
    chartTitle: 'SALES BY REGION',
    type: 'bar',
    data: [
      { label: 'North', val: '€2.4M', h: 148 },
      { label: 'South', val: '€1.8M', h: 110, alt: true },
      { label: 'East',  val: '€3.1M', h: 188 },
      { label: 'West',  val: '€2.0M', h: 122, alt: true },
      { label: 'APAC',  val: '€1.4M', h: 86 },
      { label: 'EMEA',  val: '€2.7M', h: 165 },
    ]
  },
  {
    lang: 'EN',
    prompt: 'Show me revenue trends this quarter',
    chartTitle: 'REVENUE — Q1 2026',
    type: 'line',
    points: [12, 28, 22, 38, 32, 52, 46, 68, 62, 80, 74, 95]
  },
  {
    lang: 'EN',
    prompt: 'What\'s the breakdown of users by country?',
    chartTitle: 'USER DISTRIBUTION',
    type: 'donut',
    segments: [
      { label: 'France',     pct: 34, color: '#9662FE' },
      { label: 'USA',        pct: 28, color: '#C49BFF' },
      { label: 'Germany',    pct: 18, color: '#7B4ED4' },
      { label: 'UK',         pct: 12, color: '#5E35B1' },
      { label: 'Other',      pct: 8,  color: '#3E2070' },
    ]
  },
  {
    lang: 'EN',
    prompt: 'Show a heatmap of user activity by hour and day',
    chartTitle: 'USER ACTIVITY HEATMAP',
    type: 'heatmap',
    days: ['Mon','Tue','Wed','Thu','Fri'],
    hours: ['8h','10h','12h','14h','16h','18h','20h'],
    values: [
      [0.1,0.3,0.5,0.4,0.2,0.1,0.05],
      [0.2,0.6,0.9,0.8,0.7,0.3,0.1],
      [0.15,0.5,0.85,0.95,0.6,0.25,0.08],
      [0.2,0.65,0.9,0.8,0.7,0.35,0.12],
      [0.1,0.4,0.6,0.5,0.3,0.1,0.04],
    ]
  },
  {
    lang: 'EN',
    prompt: 'Compare revenue vs expenses as a grouped bar',
    chartTitle: 'REVENUE vs EXPENSES',
    type: 'grouped',
    groups: [
      { label: 'Q1', a: 82, b: 60 },
      { label: 'Q2', a: 110, b: 75 },
      { label: 'Q3', a: 135, b: 88 },
      { label: 'Q4', a: 165, b: 100 },
    ]
  }
];

const dotsEl = document.getElementById('ds-dots');
dotsEl.innerHTML = '';
SCENES.forEach((_, i) => {
  const d = document.createElement('div');
  d.className = 'dot'; d.id = `ds-dot-${i}`;
  dotsEl.appendChild(d);
});

function setDot(i) {
  SCENES.forEach((_, j) => {
    const el = document.getElementById(`ds-dot-${j}`);
    if (el) el.className = 'dot' + (j === i ? ' active' : '');
  });
}

function buildBar(scene) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;align-items:flex-end;gap:10px;width:100%;height:100%;padding-bottom:4px;';
  scene.data.forEach(d => {
    const grp = document.createElement('div');
    grp.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:5px;flex:1;height:100%;justify-content:flex-end;';
    grp.innerHTML = `
      <div class="bar${d.alt?' alt':''}" style="width:100%;height:0;position:relative;">
        <div class="bar-val">${d.val}</div>
      </div>
      <div class="bar-label">${d.label}</div>`;
    wrap.appendChild(grp);
    setTimeout(() => {
      const bar = grp.querySelector('.bar');
      bar.style.height = d.h + 'px';
      setTimeout(() => bar.classList.add('grown'), 900);
    }, 100);
  });
  return wrap;
}

function buildLine(scene) {
  const wrap = document.createElement('div');
  wrap.className = 'line-chart-wrap';
  const pts = scene.points;
  const W = 636, H = 170;
  const maxV = Math.max(...pts);
  const minV = Math.min(...pts);
  const xs = pts.map((_, i) => (i / (pts.length - 1)) * W);
  const ys = pts.map(v => H - ((v - minV) / (maxV - minV)) * (H * 0.85) - 10);
  const pathD = xs.map((x, i) => `${i===0?'M':'L'} ${x} ${ys[i]}`).join(' ');
  const areaD = `M ${xs[0]} ${H} ` + xs.map((x,i) => `L ${x} ${ys[i]}`).join(' ') + ` L ${xs[xs.length-1]} ${H} Z`;

  wrap.innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
      <defs>
        <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#9662FE" stop-opacity="0.25"/>
          <stop offset="100%" stop-color="#9662FE" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      <path class="line-area" d="${areaD}"/>
      <path class="line-path" d="${pathD}"/>
      ${xs.map((x,i) => `<circle class="line-dot" cx="${x}" cy="${ys[i]}" r="4"/>`).join('')}
    </svg>`;

  setTimeout(() => {
    wrap.querySelector('.line-path').classList.add('drawn');
    wrap.querySelector('.line-area').classList.add('drawn');
    setTimeout(() => {
      wrap.querySelectorAll('.line-dot').forEach((d, i) => {
        setTimeout(() => { d.style.opacity = 1; }, i * 80);
      });
    }, 900);
  }, 80);
  return wrap;
}

function buildDonut(scene) {
  const wrap = document.createElement('div');
  wrap.className = 'donut-wrap';
  const R = 54, circ = 2 * Math.PI * R;
  let offset = 0;
  const segs = scene.segments.map(s => {
    const dash = (s.pct / 100) * circ;
    const gap  = circ - dash;
    const el = `<circle class="donut-circle" cx="70" cy="70" r="${R}"
      stroke="${s.color}"
      style="stroke-dasharray:0 ${circ};stroke-dashoffset:${-offset};transform-origin:70px 70px;transform:rotate(-90deg);"
    />`;
    offset += dash;
    return { el, dash, gap, color: s.color, circ, label: s.label, pct: s.pct };
  });

  const legend = scene.segments.map(s =>
    `<div class="legend-item">
      <div class="legend-dot" style="background:${s.color}"></div>
      <div class="legend-text">${s.label}</div>
      <div class="legend-pct">${s.pct}%</div>
    </div>`
  ).join('');

  wrap.innerHTML = `
    <svg class="donut-svg" width="140" height="140" viewBox="0 0 140 140">
      <circle cx="70" cy="70" r="${R}" fill="none" stroke="#2A1F2A" stroke-width="22"/>
      ${segs.map(s => s.el).join('')}
    </svg>
    <div class="donut-legend">${legend}</div>`;

  setTimeout(() => {
    segs.forEach((s, i) => {
      const circle = wrap.querySelectorAll('.donut-circle')[i];
      setTimeout(() => {
        circle.style.transition = 'stroke-dasharray 0.7s cubic-bezier(0.34,1.1,0.64,1)';
        circle.style.strokeDasharray = `${s.dash} ${s.gap}`;
      }, i * 130);
    });
  }, 80);
  return wrap;
}

function buildHeatmap(scene) {
  const wrap = document.createElement('div');
  wrap.className = 'heatmap-wrap';
  const colors = [
    'rgba(150,98,254,0.08)',
    'rgba(150,98,254,0.2)',
    'rgba(150,98,254,0.38)',
    'rgba(150,98,254,0.55)',
    'rgba(150,98,254,0.72)',
    'rgba(150,98,254,0.88)',
    '#9662FE',
  ];
  scene.days.forEach((day, di) => {
    const row = document.createElement('div');
    row.className = 'heatmap-row';
    row.innerHTML = `<div class="heatmap-label">${day}</div>`;
    scene.hours.forEach((h, hi) => {
      const cell = document.createElement('div');
      cell.className = 'heatmap-cell';
      row.appendChild(cell);
      const val = scene.values[di][hi];
      const colorIndex = Math.min(Math.floor(val * colors.length), colors.length - 1);
      setTimeout(() => {
        cell.style.background = colors[colorIndex];
      }, (di * scene.hours.length + hi) * 40 + 100);
    });
    wrap.appendChild(row);
  });
  const labRow = document.createElement('div');
  labRow.className = 'heatmap-row';
  labRow.innerHTML = `<div class="heatmap-label"></div>` +
    scene.hours.map(h => `<div style="flex:1;text-align:center;font-size:9px;color:#6B4F6B;">${h}</div>`).join('');
  wrap.appendChild(labRow);
  return wrap;
}

function buildGrouped(scene) {
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:flex;align-items:flex-end;gap:16px;width:100%;height:100%;padding-bottom:4px;';
  const maxH = 160;
  const maxVal = Math.max(...scene.groups.flatMap(g => [g.a, g.b]));
  scene.groups.forEach(g => {
    const grp = document.createElement('div');
    grp.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:5px;flex:1;height:100%;justify-content:flex-end;';
    const ha = Math.round((g.a / maxVal) * maxH);
    const hb = Math.round((g.b / maxVal) * maxH);
    grp.innerHTML = `
      <div style="display:flex;gap:4px;align-items:flex-end;width:100%;">
        <div style="flex:1;border-radius:5px 5px 0 0;height:0;background:linear-gradient(180deg,#9662FE,#7B4ED4);transition:height 1.2s cubic-bezier(0.34,1.2,0.64,1);position:relative;">
          <div style="position:absolute;top:-16px;left:50%;transform:translateX(-50%);font-size:9px;color:#9662FE;font-weight:700;white-space:nowrap;opacity:0;transition:opacity 0.4s 1s;">€${g.a}k</div>
        </div>
        <div style="flex:1;border-radius:5px 5px 0 0;height:0;background:linear-gradient(180deg,#C49BFF,#9662FE);opacity:0.5;transition:height 1.2s cubic-bezier(0.34,1.2,0.64,1) 0.1s;"></div>
      </div>
      <div class="bar-label">${g.label}</div>`;
    wrap.appendChild(grp);
    setTimeout(() => {
      const bars = grp.querySelectorAll('div[style*="height:0"]');
      bars[0].style.height = ha + 'px';
      bars[1].style.height = hb + 'px';
      setTimeout(() => { bars[0].querySelector('div').style.opacity = 1; }, 1000);
    }, 100);
  });

  const legend = document.createElement('div');
  legend.style.cssText = 'position:absolute;top:2px;right:0;display:flex;gap:14px;';
  legend.innerHTML = `
    <div style="display:flex;align-items:center;gap:5px;">
      <div style="width:10px;height:10px;border-radius:3px;background:#9662FE;"></div>
      <span style="font-size:10px;color:#CDBACF;">Revenue</span>
    </div>
    <div style="display:flex;align-items:center;gap:5px;">
      <div style="width:10px;height:10px;border-radius:3px;background:#C49BFF;opacity:0.5;"></div>
      <span style="font-size:10px;color:#CDBACF;">Expenses</span>
    </div>`;
  return { main: wrap, legend };
}

function typeText(el, text, cb) {
  el.innerHTML = '<span class="cursor-blinkDs"></span>';
  let i = 0;
  const interval = setInterval(() => {
    if (i >= text.length) {
      clearInterval(interval);
      if (cb) setTimeout(cb, 300);
      return;
    }
    el.innerHTML = text.slice(0, ++i) + '<span class="cursor-blinkDs"></span>';
  }, 38);
}

function eraseText(el, cb) {
  let text = el.textContent.replace('|', '').trim();
  let i = text.length;
  const interval = setInterval(() => {
    if (i <= 0) {
      clearInterval(interval);
      el.innerHTML = '<span class="cursor-blinkDs"></span>';
      if (cb) setTimeout(cb, 200);
      return;
    }
    el.innerHTML = text.slice(0, --i) + '<span class="cursor-blinkDs"></span>';
  }, 22);
}

const chartArea = document.getElementById('ds-chartArea');
const inputText = document.getElementById('ds-inputText');
const inputBar  = document.getElementById('ds-inputBar');
const sendBtn   = document.getElementById('ds-sendBtn');
const langBadge = document.getElementById('ds-langBadge');
let sceneTimeout = null;

function showScene(index) {
  const scene = SCENES[index];
  setDot(index);

  langBadge.textContent = scene.lang;

  inputBar.classList.add('active');
  sendBtn.classList.remove('ready');

  typeText(inputText, scene.prompt, () => {
    sendBtn.classList.add('ready');

    const card = document.createElement('div');
    card.className = 'chart-card';

    const titleEl = document.createElement('div');
    titleEl.className = 'chart-title';
    titleEl.textContent = scene.chartTitle;
    card.appendChild(titleEl);

    const body = document.createElement('div');
    body.className = 'chart-body';
    body.style.position = 'relative';

    let chartEl;
    if (scene.type === 'bar') {
      chartEl = buildBar(scene);
      body.classList.add('bar-chart');
    } else if (scene.type === 'line') {
      chartEl = buildLine(scene);
    } else if (scene.type === 'donut') {
      chartEl = buildDonut(scene);
    } else if (scene.type === 'heatmap') {
      chartEl = buildHeatmap(scene);
    } else if (scene.type === 'grouped') {
      const res = buildGrouped(scene);
      chartEl = res.main;
      card.appendChild(res.legend);
    }

    body.appendChild(chartEl);
    card.appendChild(body);
    chartArea.appendChild(card);

    requestAnimationFrame(() => requestAnimationFrame(() => card.classList.add('visible')));

    sceneTimeout = setTimeout(() => {
      card.classList.add('hiding');
      eraseText(inputText, () => {
        inputBar.classList.remove('active');
        sendBtn.classList.remove('ready');
        setTimeout(() => {
          card.remove();
          showScene((index + 1) % SCENES.length);
        }, 200);
      });
    }, 3800);
  });
}

showScene(0);

}

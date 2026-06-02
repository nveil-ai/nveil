// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

/* Upload Animation */
export function init() {

const __rootEl = document.getElementById('up-stage');
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

const FILES = [
  {
    ext: 'CSV',
    label: 'Spreadsheet · CSV',
    bg: 'linear-gradient(145deg, #0d3d22, #165c30)',
    color: '#4ADE80',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <rect x="4"  y="7"  width="28" height="3.5" rx="1.75" fill="#4ADE80" opacity="0.95"/>
      <rect x="4"  y="14" width="28" height="3.5" rx="1.75" fill="#4ADE80" opacity="0.6"/>
      <rect x="4"  y="21" width="18" height="3.5" rx="1.75" fill="#4ADE80" opacity="0.35"/>
      <rect x="4"  y="28" width="22" height="3.5" rx="1.75" fill="#4ADE80" opacity="0.2"/>
      <rect x="3.5" y="6" width="1.5" height="27" rx="0.75" fill="#4ADE80" opacity="0.3"/>
      <rect x="13"  y="6" width="1.5" height="27" rx="0.75" fill="#4ADE80" opacity="0.2"/>
    </svg>`
  },
  {
    ext: 'XLSX',
    label: 'Excel · XLSX',
    bg: 'linear-gradient(145deg, #0f3a1b, #1a5e27)',
    color: '#86EFAC',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <path d="M7 9 L15 18 L7 27"  stroke="#86EFAC" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M29 9 L21 18 L29 27" stroke="#86EFAC" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="13" y1="18" x2="23" y2="18" stroke="#86EFAC" stroke-width="1.5" stroke-linecap="round" opacity="0.45"/>
    </svg>`
  },
  {
    ext: 'XML',
    label: 'Markup · XML',
    bg: 'linear-gradient(145deg, #2a1a08, #4a2e0a)',
    color: '#FB923C',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <path d="M5 10 L12 18 L5 26"  stroke="#FB923C" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <path d="M31 10 L24 18 L31 26" stroke="#FB923C" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
      <line x1="16" y1="8" x2="20" y2="28" stroke="#FB923C" stroke-width="2" stroke-linecap="round" opacity="0.55"/>
    </svg>`
  },
  {
    ext: 'JSON',
    label: 'API · JSON',
    bg: 'linear-gradient(145deg, #3a2708, #61420e)',
    color: '#FCD34D',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <path d="M11 7C9 7 7 8.8 7 11v3.5c0 1.8-1.4 2.8-2.5 3 1.1.2 2.5 1.2 2.5 3V24c0 2.2 2 4 4 4" stroke="#FCD34D" stroke-width="2" stroke-linecap="round"/>
      <path d="M25 7c2 0 4 1.8 4 4v3.5c0 1.8 1.4 2.8 2.5 3-1.1.2-2.5 1.2-2.5 3V24c0 2.2-2 4-4 4" stroke="#FCD34D" stroke-width="2" stroke-linecap="round"/>
      <circle cx="15" cy="18" r="2" fill="#FCD34D"/>
      <circle cx="21" cy="18" r="2" fill="#FCD34D" opacity="0.45"/>
    </svg>`
  },
  {
    ext: 'DICOM',
    label: 'Medical · DICOM',
    bg: 'linear-gradient(145deg, #0a2e50, #10476e)',
    color: '#38BDF8',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <circle cx="18" cy="18" r="13" stroke="#38BDF8" stroke-width="1.2" opacity="0.3"/>
      <circle cx="18" cy="18" r="8"  stroke="#38BDF8" stroke-width="1.2" opacity="0.6"/>
      <circle cx="18" cy="18" r="3"  fill="#38BDF8"/>
      <line x1="18" y1="4"  x2="18" y2="8"  stroke="#38BDF8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="18" y1="28" x2="18" y2="32" stroke="#38BDF8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="4"  y1="18" x2="8"  y2="18" stroke="#38BDF8" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="28" y1="18" x2="32" y2="18" stroke="#38BDF8" stroke-width="1.5" stroke-linecap="round"/>
    </svg>`
  },
  {
    ext: 'MHD',
    label: 'Medical · MHD',
    bg: 'linear-gradient(145deg, #1a0a3a, #2e1060)',
    color: '#C084FC',
    icon: `<svg viewBox="0 0 36 36" fill="none">
      <rect x="5"  y="5"  width="26" height="26" rx="6" stroke="#C084FC" stroke-width="1.3" opacity="0.3"/>
      <rect x="9"  y="9"  width="18" height="18" rx="4" stroke="#C084FC" stroke-width="1.3" opacity="0.6"/>
      <path d="M12 18 L15 14 L18 20 L21 16 L24 18" stroke="#C084FC" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`
  }
];

let animTimeout = null;
const fileArea  = __rootEl.querySelector('#up-fileArea');
const inputBar  = __rootEl.querySelector('#up-inputBar');
const dotsEl    = __rootEl.querySelector('#up-dots');
const replayBtn = __rootEl.querySelector('#up-replayBtn');

dotsEl.innerHTML = '';
FILES.forEach((_, i) => {
  const d = document.createElement('div');
  d.className = 'dot';
  d.id = `up-dot-${i}`;
  dotsEl.appendChild(d);
});

function buildCards() {
  fileArea.innerHTML = '';
  FILES.forEach((f, i) => {
    const card = document.createElement('div');
    card.className = 'file-card';
    card.id = `card-${i}`;
    card.innerHTML = `
      <div class="file-icon-wrap">
        <div class="file-body" style="background:${f.bg};">
          <div class="file-fold"></div>
          <div class="icon-svg">${f.icon}</div>
          <div class="file-ext" style="color:${f.color};">${f.ext}</div>
        </div>
      </div>
      <div class="file-badge">${f.label}</div>
    `;
    fileArea.appendChild(card);
  });
}

function setDot(index) {
  FILES.forEach((_, i) => {
    const el = __rootEl.querySelector(`#up-dot-${i}`);
    if (el) el.className = 'dot' + (i === index ? ' active' : '');
  });
}

function showCard(index) {
  const card = __rootEl.querySelector(`#card-${index}`);
  card.className = 'file-card active';
  setDot(index);
  setTimeout(() => inputBar.classList.add('glowing'), 420);
}

function hideCard(index, cb) {
  __rootEl.querySelector(`#card-${index}`).className = 'file-card exiting';
  inputBar.classList.remove('glowing');
  setTimeout(cb, 300);
}

function runSequence(index) {
  if (index >= FILES.length) {
    replayBtn.classList.add('visible');
    animTimeout = setTimeout(() => startAnimation(), 1800);
    return;
  }
  showCard(index);
  animTimeout = setTimeout(() => {
    hideCard(index, () => runSequence(index + 1));
  }, 2200);
}

function startAnimation() {
  clearTimeout(animTimeout);
  replayBtn.classList.remove('visible');
  inputBar.classList.remove('glowing');
  buildCards();
  setTimeout(() => runSequence(0), 300);
}

startAnimation();

replayBtn.onclick = startAnimation;
}

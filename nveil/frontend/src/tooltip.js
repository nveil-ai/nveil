// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Smart tooltip — position: fixed, escapes all overflow: hidden ancestors.
 *
 * Reads the `data-tooltip` attribute. Defaults to above the trigger element;
 * falls back to below when there isn't enough space above the viewport edge.
 * Horizontal position is centered and clamped to the viewport.
 *
 * A single shared DOM node is reused for all tooltips (no per-element overhead).
 */

const GAP = 6;    // px between trigger edge and tooltip box
const MARGIN = 8; // min px from viewport edge

const tip = document.createElement('div');
tip.className = 'tooltip-root';
document.body.appendChild(tip);

let currentTarget = null;

function show(el) {
    const text = el.dataset.tooltip;
    if (!text) return;

    tip.textContent = text;

    // Measure in hidden state to get correct dimensions before painting
    tip.style.visibility = 'hidden';
    tip.style.display = 'block';

    const r = el.getBoundingClientRect();
    const t = tip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Vertical: prefer above, fall back to below
    let top = r.top - t.height - GAP;
    if (top < MARGIN) top = r.bottom + GAP;

    // Horizontal: center on trigger, then clamp to viewport
    let left = r.left + r.width / 2 - t.width / 2;
    left = Math.max(MARGIN, Math.min(left, vw - t.width - MARGIN));

    tip.style.top = `${top}px`;
    tip.style.left = `${left}px`;
    tip.style.visibility = 'visible';
}

function hide() {
    tip.style.display = 'none';
    currentTarget = null;
}

// Event delegation — one listener for the whole document
document.addEventListener('mouseover', (e) => {
    const el = e.target.closest('[data-tooltip]');
    if (el === currentTarget) return;
    currentTarget = el;
    if (el) show(el);
    else hide();
});

// Hide when mouse leaves the viewport entirely
document.addEventListener('mouseleave', hide);

// Hide on any scroll so stale positions never show
document.addEventListener('scroll', hide, { capture: true, passive: true });

// Hide on resize (positions become invalid)
window.addEventListener('resize', hide, { passive: true });

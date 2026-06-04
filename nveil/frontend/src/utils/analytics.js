// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// src/utils/analytics.js
// All tracking is managed by Google Tag Manager (loaded from index.html only
// when a VITE_GTM_ID is configured at build time — disabled in self-hosting).
// This module only pushes semantic events to the dataLayer.
// Pixel-specific code (GA4, Reddit, LinkedIn…) lives in GTM, not here.

// ---------------------------------------------------------------------------
// dataLayer helper
// ---------------------------------------------------------------------------
function push(obj) {
  window.dataLayer = window.dataLayer || [];
  window.dataLayer.push(obj);
}

// ---------------------------------------------------------------------------
// Cookie helper (fast, no React dependency — avoids race conditions)
// ---------------------------------------------------------------------------
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

// ---------------------------------------------------------------------------
// Consent  (GDPR — Consent Mode v2)
// ---------------------------------------------------------------------------

/**
 * Called once from index.html BEFORE the GTM script tag.
 * Sets all consent signals to "denied" by default (EU requirement).
 *
 * If the visitor already accepted cookies on a previous visit, we
 * immediately upgrade consent so GTM tags can fire on first page load
 * without waiting for the React CookieBanner component to mount.
 */
export function installConsentDefaults() {
  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = gtag;

  // 1. Default: everything denied (GDPR safe)
  gtag("consent", "default", {
    ad_storage:          "denied",
    ad_user_data:        "denied",
    ad_personalization:  "denied",
    analytics_storage:   "denied",
    wait_for_update:     500,       // ms — gives CMP time to load saved prefs
  });

  // 2. If returning visitor already accepted, upgrade immediately
  const saved = getCookie("cookieConsent");
  if (saved === "true") {
    gtag("consent", "update", {
      ad_storage:          "granted",
      ad_user_data:        "granted",
      ad_personalization:  "granted",
      analytics_storage:   "granted",
    });
  }

  // 3. Capture ad-platform click IDs (Reddit rdt_cid, etc.)
  captureClickIds();
}

// ---------------------------------------------------------------------------
// Consent update  (called by CookieBanner)
// ---------------------------------------------------------------------------
export function updateConsent(granted) {
  const value = granted ? "granted" : "denied";
  if (window.gtag) {
    window.gtag("consent", "update", {
      ad_storage:          value,
      ad_user_data:        value,
      ad_personalization:  value,
      analytics_storage:   value,
    });
  }
  // Fire a custom event so GTM triggers can react to the consent change
  push({ event: "consent_update", consent_granted: granted });
}

// ---------------------------------------------------------------------------
// Click-ID capture  (stores ad-platform click IDs for GTM to read)
// ---------------------------------------------------------------------------
function captureClickIds() {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);

  // Reddit
  const rdtCid = params.get("rdt_cid");
  if (rdtCid) sessionStorage.setItem("rdt_cid", rdtCid);

  // LinkedIn (li_fat_id is LinkedIn's click ID)
  const liFat = params.get("li_fat_id");
  if (liFat) sessionStorage.setItem("li_fat_id", liFat);
}

// ---------------------------------------------------------------------------
// Event helpers  (push to dataLayer — GTM fires the right tags)
// ---------------------------------------------------------------------------

/** Generic analytics event */
export function trackEvent(eventName, params = {}) {
  push({ event: eventName, ...params });
}

/** Page view — called by RouteTracker on every route change */
export function trackPageView(path) {
  push({ event: "virtual_pageview", page_path: path });
}

/** Signup conversion — called after successful registration */
export function trackSignup(email) {
  push({
    event: "sign_up",
    method: "email",
    user_email: email,   // GTM can hash this before sending to ad platforms
  });
}

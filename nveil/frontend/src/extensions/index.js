// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

/**
 * Frontend extension system.
 *
 * Tries to dynamically import `@nveil/cloud-frontend`.  If the package is
 * not installed (community edition), every getter returns a safe default
 * (empty array, null component, etc.).
 *
 * Extensions export:
 *   routes   – array of { path, element } for React Router
 *   navItems – array of { path, icon, labelKey } for NavBar
 *   LicenseDisplay – component for the Settings subscription section
 */

let _cloud = null;
let _loaded = false;
let _listeners = [];

async function _load() {
    if (_loaded) return _cloud;
    try {
        _cloud = await import("@nveil/cloud-frontend");
    } catch {
        _cloud = null;
    }
    _loaded = true;
    _listeners.forEach(fn => fn());
    _listeners = [];
    return _cloud;
}

export const extensionsReady = _load();

export function onExtensionsLoaded(fn) {
    if (_loaded) { fn(); return; }
    _listeners.push(fn);
}

export function getExtensionRoutes() {
    return _cloud?.routes ?? [];
}

export function getExtensionNavItems() {
    return _cloud?.navItems ?? [];
}

export function getLicenseDisplay() {
    return _cloud?.LicenseDisplay ?? null;
}

export function hasExtension(name) {
    if (!_cloud) return false;
    return typeof _cloud[name] !== "undefined";
}

export function hasBilling() {
    return _cloud?.hasBilling ?? false;
}

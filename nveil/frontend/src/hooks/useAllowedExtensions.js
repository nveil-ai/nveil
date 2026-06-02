// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect } from 'react';

// Module-level cache so we fetch only once across all components
let _cached = null;
let _promise = null;

/**
 * Hook that fetches the list of accepted file extensions from the backend.
 * The file_service is the single source of truth — no hardcoded lists needed.
 *
 * Returns { extensions: string[], accept: string, loading: boolean }
 *   - extensions: array like [".csv", ".json", ".mat", ...]
 *   - accept: comma-joined string for <input accept="...">
 *   - loading: true while fetching
 */
export default function useAllowedExtensions() {
    const [extensions, setExtensions] = useState(_cached || []);
    const [loading, setLoading] = useState(!_cached);

    useEffect(() => {
        if (_cached) return;

        if (!_promise) {
            _promise = fetch('/server/extensions', { credentials: 'include' })
                .then(res => res.ok ? res.json() : null)
                .then(data => {
                    _cached = data?.extensions || [];
                    return _cached;
                })
                .catch(() => {
                    _cached = [];
                    return _cached;
                });
        }

        _promise.then(exts => {
            setExtensions(exts);
            setLoading(false);
        });
    }, []);

    return {
        extensions,
        accept: extensions.join(','),
        loading,
    };
}

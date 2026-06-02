// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect, useCallback, useRef } from 'react';

/**
 * Bidirectional state sync between React and trame.
 *
 * Follows the trame-react example pattern:
 * - Watch: comm.state.watch([key], callback)
 * - Push: comm.state.update({key: value})
 * - Read: comm.state.get() returns full state
 */
export default function useTrameState(communicatorRef, key, defaultValue, prefix = '') {
    const [value, setValue] = useState(defaultValue);
    const prefixedKey = prefix + key;
    const timerRef = useRef(null);

    // Watch trame state for this key
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state) return;

        comm.state.watch([prefixedKey], (newVal) => {
            if (newVal !== undefined) {
                setValue(newVal);
            }
        });
    }, [communicatorRef?.current, prefixedKey]);

    // Push changes to trame — exact pattern from example: debounced state.update()
    const onChange = useCallback((newVal) => {
        setValue(newVal);

        clearTimeout(timerRef.current);
        timerRef.current = setTimeout(() => {
            const comm = communicatorRef?.current;
            if (!comm?.state) return;

            // Same pattern as example: get current state, compare, update if different
            comm.state.get().then((trameState) => {
                if (trameState?.[prefixedKey] !== newVal) {
                    comm.state.update({ [prefixedKey]: newVal });
                }
            }).catch(() => {
                // Fallback: just update directly
                comm.state.update({ [prefixedKey]: newVal });
            });
        }, 25);
    }, [communicatorRef, prefixedKey]);

    useEffect(() => () => clearTimeout(timerRef.current), []);

    return [value, onChange];
}

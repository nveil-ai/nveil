// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useRef, useCallback, useState, useLayoutEffect } from 'react';

const MIN_W = 320;
const MIN_H = 200;

export default function useFloatingWindow(containerRef, bodyRef) {
    const [minimized, setMinimized] = useState(false);
    const pos = useRef({ left: 16, bottom: 16, width: 420, height: 600 });
    const savedHeight = useRef(600);
    const interaction = useRef(null);

    // Apply position, size, and minimized state to DOM every render.
    // Runs as layout effect so there's no visual flash.
    useLayoutEffect(() => {
        const el = containerRef.current;
        if (!el) return;
        const p = pos.current;
        el.style.left = p.left + 'px';
        el.style.bottom = p.bottom + 'px';
        el.style.top = 'auto';
        el.style.right = 'auto';
        el.style.width = p.width + 'px';
        if (minimized) {
            el.style.height = 'auto';
            if (bodyRef.current) bodyRef.current.style.display = 'none';
        } else {
            el.style.height = p.height + 'px';
            if (bodyRef.current) bodyRef.current.style.display = '';
        }
    });

    const applyPos = useCallback(() => {
        const el = containerRef.current;
        if (!el) return;
        const p = pos.current;
        el.style.left = p.left + 'px';
        el.style.bottom = p.bottom + 'px';
        el.style.top = 'auto';
        el.style.right = 'auto';
        el.style.width = p.width + 'px';
        el.style.height = p.height + 'px';
    }, [containerRef]);

    // --- Drag (header) ---
    const onDragStart = useCallback((e) => {
        if (e.target.closest('button')) return;
        interaction.current = { type: 'drag', sx: e.clientX, sy: e.clientY, sp: { ...pos.current } };
        e.currentTarget.setPointerCapture(e.pointerId);
    }, []);

    const onDragMove = useCallback((e) => {
        const i = interaction.current;
        if (!i || i.type !== 'drag') return;
        const el = containerRef.current;
        if (!el) return;
        let left = i.sp.left + (e.clientX - i.sx);
        let bottom = i.sp.bottom - (e.clientY - i.sy);
        left = Math.max(0, Math.min(left, window.innerWidth - el.offsetWidth));
        bottom = Math.max(0, Math.min(bottom, window.innerHeight - el.offsetHeight));
        pos.current.left = left;
        pos.current.bottom = bottom;
        el.style.left = left + 'px';
        el.style.bottom = bottom + 'px';
    }, [containerRef]);

    const onDragEnd = useCallback(() => { interaction.current = null; }, []);

    // --- Resize (edges/corners) ---
    const onResizeStart = useCallback((edge, e) => {
        interaction.current = { type: edge, sx: e.clientX, sy: e.clientY, sp: { ...pos.current } };
        e.currentTarget.setPointerCapture(e.pointerId);
        e.stopPropagation();
    }, []);

    const onResizeMove = useCallback((e) => {
        const i = interaction.current;
        if (!i || i.type === 'drag') return;
        const el = containerRef.current;
        if (!el) return;
        const dx = e.clientX - i.sx;
        const dy = e.clientY - i.sy;
        const edge = i.type;
        const b = { ...i.sp };

        if (edge.includes('e')) b.width = Math.max(MIN_W, i.sp.width + dx);
        if (edge.includes('w')) {
            const nw = Math.max(MIN_W, i.sp.width - dx);
            b.left = i.sp.left + i.sp.width - nw;
            b.width = nw;
        }
        if (edge.includes('n')) b.height = Math.max(MIN_H, i.sp.height - dy);
        if (edge.includes('s')) {
            const nh = Math.max(MIN_H, i.sp.height + dy);
            b.bottom = i.sp.bottom - (nh - i.sp.height);
            b.height = nh;
            if (b.bottom < 0) { b.height += b.bottom; b.bottom = 0; if (b.height < MIN_H) b.height = MIN_H; }
        }

        // Viewport clamp
        b.left = Math.max(0, b.left);
        b.bottom = Math.max(0, b.bottom);
        if (b.left + b.width > window.innerWidth) b.width = window.innerWidth - b.left;
        if (b.bottom + b.height > window.innerHeight) b.height = window.innerHeight - b.bottom;
        b.width = Math.max(MIN_W, b.width);
        b.height = Math.max(MIN_H, b.height);

        pos.current = b;
        applyPos();
    }, [containerRef, applyPos]);

    const onResizeEnd = useCallback(() => { interaction.current = null; }, []);

    // --- Minimize / Restore ---
    const toggleMinimize = useCallback(() => {
        setMinimized(prev => {
            if (!prev) {
                savedHeight.current = pos.current.height;
            } else {
                pos.current.height = savedHeight.current;
                const maxH = window.innerHeight - pos.current.bottom;
                if (pos.current.height > maxH) pos.current.height = Math.max(MIN_H, maxH);
            }
            return !prev;
        });
    }, []);

    const reset = useCallback(() => {
        pos.current = { left: 16, bottom: 16, width: 420, height: 600 };
        savedHeight.current = 600;
        setMinimized(false);
    }, []);

    return {
        minimized,
        toggleMinimize,
        dragHandlers: { onPointerDown: onDragStart, onPointerMove: onDragMove, onPointerUp: onDragEnd },
        onResizeStart, onResizeMove, onResizeEnd,
        reset,
    };
}

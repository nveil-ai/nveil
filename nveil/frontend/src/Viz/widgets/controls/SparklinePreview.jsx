// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useMemo, useId } from 'react';
import styles from './SparklinePreview.module.css';

/**
 * SVG sparkline for opacity/transfer function preview.
 * Renders a filled area chart using the real color palette gradient
 * when `colors` is provided (from trame state).
 */
export default function SparklinePreview({ values = [], colors = [], height = 120 }) {
    const id = useId();
    const gradId = `spark-${id}`;

    const MIN_OPACITY = 0.06;

    const path = useMemo(() => {
        if (!values.length) return '';
        const n = values.length;
        const w = 100;
        const points = values.map((v, i) => {
            const x = (i / (n - 1)) * w;
            const clamped = Math.max(MIN_OPACITY, v);
            const y = height - clamped * height;
            return `${x},${y}`;
        });
        return `M0,${height} L${points.join(' L')} L${w},${height} Z`;
    }, [values, height]);

    const gradient = useMemo(() => {
        if (!colors.length) return null;
        return colors.map((c, i) => ({
            offset: `${(i / Math.max(1, colors.length - 1)) * 100}%`,
            color: typeof c === 'string' ? c : `rgb(${c[0]},${c[1]},${c[2]})`,
        }));
    }, [colors]);

    if (!values.length) return null;

    const fill = gradient ? `url(#${gradId})` : 'rgba(27, 144, 186, 0.3)';
    const stroke = gradient ? `url(#${gradId})` : 'rgba(27, 144, 186, 0.6)';

    return (
        <div className={styles.wrapper}>
            <svg
                viewBox={`0 0 100 ${height}`}
                preserveAspectRatio="none"
                className={styles.svg}
            >
                <defs>
                    {gradient && (
                        <linearGradient id={gradId} x1="0" x2="1" y1="0" y2="0">
                            {gradient.map((g, i) => (
                                <stop key={i} offset={g.offset} stopColor={g.color} stopOpacity="0.85" />
                            ))}
                        </linearGradient>
                    )}
                </defs>
                <path
                    d={path}
                    fill={fill}
                    stroke={stroke}
                    strokeWidth="0.5"
                />
            </svg>
        </div>
    );
}

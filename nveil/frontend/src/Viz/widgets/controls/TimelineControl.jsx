// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect, useCallback, useRef } from 'react';
import { Slider, SliderTrack, SliderThumb } from 'react-aria-components';
import {
    MdSkipPrevious,
    MdSkipNext,
    MdPlayArrow,
    MdPause,
    MdNavigateBefore,
    MdNavigateNext,
} from 'react-icons/md';
import styles from './TimelineControl.module.css';

export default function TimelineControl({
    count,
    labels,
    current,
    playing,
    fps,
    onChange,
    onPlayToggle,
    onFpsChange,
    inline,
}) {
    const FPS_OPTIONS = [0.5, 1, 2, 4, 10];
    const [fpsIdx, setFpsIdx] = useState(() => {
        const idx = FPS_OPTIONS.indexOf(fps);
        return idx >= 0 ? idx : 2;
    });

    const containerRef = useRef(null);

    const label = labels?.[current] ?? `${current}`;

    const stepBy = useCallback(
        (delta) => {
            const next = Math.max(0, Math.min(count - 1, current + delta));
            if (next !== current) onChange(next);
        },
        [current, count, onChange]
    );

    const goFirst = useCallback(() => onChange(0), [onChange]);
    const goLast = useCallback(() => onChange(count - 1), [count, onChange]);

    const togglePlay = useCallback(() => {
        onPlayToggle(!playing);
    }, [playing, onPlayToggle]);

    const cycleFps = useCallback(() => {
        const next = (fpsIdx + 1) % FPS_OPTIONS.length;
        setFpsIdx(next);
        onFpsChange(FPS_OPTIONS[next]);
    }, [fpsIdx, onFpsChange]);

    // Keyboard shortcuts
    useEffect(() => {
        const handler = (e) => {
            // Only handle when this component or its ancestors have focus,
            // or when no input/textarea is focused
            const active = document.activeElement;
            if (active?.tagName === 'INPUT' || active?.tagName === 'TEXTAREA'
                || active?.isContentEditable || active?.closest('[contenteditable]')) return;

            if (e.key === ' ' || e.code === 'Space') {
                e.preventDefault();
                togglePlay();
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                stepBy(-1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                stepBy(1);
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [togglePlay, stepBy]);

    if (count <= 1) return null;

    return (
        <div className={inline ? styles.timelineInline : styles.timeline} ref={containerRef}>
            <div className={styles.controls}>
                <button className={styles.btn} onClick={goFirst} data-tooltip="First frame" aria-label="First frame">
                    <MdSkipPrevious />
                </button>
                <button className={styles.btn} onClick={() => stepBy(-1)} data-tooltip="Previous frame" aria-label="Previous frame">
                    <MdNavigateBefore />
                </button>
                <button className={`${styles.btn} ${styles.playBtn}`} onClick={togglePlay} data-tooltip={playing ? 'Pause' : 'Play'} aria-label={playing ? 'Pause' : 'Play'}>
                    {playing ? <MdPause /> : <MdPlayArrow />}
                </button>
                <button className={styles.btn} onClick={() => stepBy(1)} data-tooltip="Next frame" aria-label="Next frame">
                    <MdNavigateNext />
                </button>
                <button className={styles.btn} onClick={goLast} data-tooltip="Last frame" aria-label="Last frame">
                    <MdSkipNext />
                </button>
            </div>

            <Slider
                className={styles.slider}
                minValue={0}
                maxValue={count - 1}
                step={1}
                value={current}
                onChange={onChange}
                aria-label="Timeline"
            >
                <SliderTrack className={styles.track}>
                    {({ state }) => {
                        const pct = count > 1 ? state.getThumbPercent(0) * 100 : 0;
                        return (
                            <>
                                <div
                                    className={styles.trackFill}
                                    style={{ width: `${pct}%` }}
                                />
                                <SliderThumb className={styles.thumb} />
                            </>
                        );
                    }}
                </SliderTrack>
            </Slider>

            <span className={styles.label} title={label}>
                {current + 1}/{count}
            </span>

            <button className={styles.speedBtn} onClick={cycleFps} data-tooltip={`Speed: ${FPS_OPTIONS[fpsIdx]}x`} aria-label={`Speed ${FPS_OPTIONS[fpsIdx]}x`}>
                {FPS_OPTIONS[fpsIdx]}x
            </button>
        </div>
    );
}

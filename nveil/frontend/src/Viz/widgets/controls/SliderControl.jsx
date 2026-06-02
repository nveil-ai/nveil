// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useRef, useCallback, useEffect } from 'react';
import { Slider, SliderTrack, SliderThumb, SliderOutput } from 'react-aria-components';
import { getIcon } from '../iconMap';
import styles from './SliderControl.module.css';

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/**
 * Digit-selector editor: renders each character as its own span,
 * with a highlighted rectangle on the active digit.
 * Up/Down increment the selected digit, Left/Right move selection,
 * number keys replace the digit, Backspace deletes, period inserts decimal.
 */
function DigitEditor({ text, setText, selectedIdx, setSelectedIdx, onCommit, onCancel, onChange, min, max }) {
    const containerRef = useRef(null);

    useEffect(() => {
        containerRef.current?.focus();
    }, []);

    const chars = text.split('');

    // Find a valid digit index (skip dot and minus)
    const findDigitIndex = (from, dir) => {
        let i = from;
        while (i >= 0 && i < chars.length) {
            if (chars[i] !== '.' && chars[i] !== '-') return i;
            i += dir;
        }
        return -1;
    };

    const getPlaceValue = (idx) => {
        const dotIdx = text.indexOf('.');
        if (dotIdx === -1) {
            return Math.pow(10, chars.length - 1 - idx);
        }
        if (idx < dotIdx) {
            return Math.pow(10, dotIdx - 1 - idx);
        }
        // After dot
        return Math.pow(10, -(idx - dotIdx));
    };

    const applyDelta = (delta) => {
        const num = parseFloat(text) || 0;
        const result = num + delta;
        const clamped = clamp(result, min, max);
        // Preserve precision from the text
        const dotIdx = text.indexOf('.');
        const prec = dotIdx === -1 ? 0 : text.length - dotIdx - 1;
        const nextText = clamped.toFixed(prec);
        setText(nextText);
        onChange(clamped);
        // Keep selection at same index, clamped to new length
        setSelectedIdx(prev => Math.min(prev, nextText.length - 1));
    };

    const handleKeyDown = (e) => {
        e.preventDefault();
        e.stopPropagation();

        if (e.key === 'Enter') {
            onCommit();
            return;
        }
        if (e.key === 'Escape') {
            onCancel();
            return;
        }
        if (e.key === 'ArrowLeft') {
            const next = findDigitIndex(selectedIdx - 1, -1);
            if (next >= 0) setSelectedIdx(next);
            return;
        }
        if (e.key === 'ArrowRight') {
            const next = findDigitIndex(selectedIdx + 1, 1);
            if (next >= 0) {
                setSelectedIdx(next);
            } else {
                // At the end — append a new 0 digit to increase precision
                const dotIdx = text.indexOf('.');
                const newText = dotIdx === -1 ? text + '.0' : text + '0';
                setText(newText);
                setSelectedIdx(newText.length - 1);
            }
            return;
        }
        if (e.key === 'ArrowUp') {
            if (chars[selectedIdx] !== '.' && chars[selectedIdx] !== '-') {
                applyDelta(getPlaceValue(selectedIdx));
            }
            return;
        }
        if (e.key === 'ArrowDown') {
            if (chars[selectedIdx] !== '.' && chars[selectedIdx] !== '-') {
                applyDelta(-getPlaceValue(selectedIdx));
            }
            return;
        }
        // Number key — replace current digit, or append if on last digit
        if (e.key >= '0' && e.key <= '9') {
            const isLastDigit = findDigitIndex(selectedIdx + 1, 1) === -1;
            let newText;
            let nextSelectedIdx;

            if (isLastDigit) {
                // On last digit: replace it AND append the new digit
                const newChars = [...chars];
                if (chars[selectedIdx] !== '.' && chars[selectedIdx] !== '-') {
                    newChars[selectedIdx] = chars[selectedIdx]; // keep current
                }
                // Append new digit (add dot first if needed)
                const base = newChars.join('');
                newText = base.includes('.') ? base + e.key : base + '.' + e.key;
                nextSelectedIdx = newText.length - 1;
            } else {
                // Not last digit: replace in place and advance
                const newChars = [...chars];
                if (chars[selectedIdx] !== '.' && chars[selectedIdx] !== '-') {
                    newChars[selectedIdx] = e.key;
                }
                newText = newChars.join('');
                nextSelectedIdx = findDigitIndex(selectedIdx + 1, 1);
            }

            const num = parseFloat(newText);
            if (!isNaN(num)) {
                const clamped = clamp(num, min, max);
                const dotIdx = newText.indexOf('.');
                const prec = dotIdx === -1 ? 0 : newText.length - dotIdx - 1;
                const finalText = clamped.toFixed(prec);
                setText(finalText);
                onChange(clamped);
                setSelectedIdx(Math.min(nextSelectedIdx, finalText.length - 1));
            }
            return;
        }
        // Period — add decimal point if not present
        if (e.key === '.' && !text.includes('.')) {
            const newText = text + '.0';
            setText(newText);
            // Select the new digit after the dot
            setSelectedIdx(newText.length - 1);
            return;
        }
        // Backspace — remove last digit (add precision control)
        if (e.key === 'Backspace') {
            if (chars.length > 1) {
                const dotIdx = text.indexOf('.');
                // If there are decimal digits, remove the last one
                if (dotIdx !== -1 && text.length - dotIdx > 1) {
                    const newText = text.slice(0, -1);
                    // If only dot remains at end, remove it too
                    const finalText = newText.endsWith('.') ? newText.slice(0, -1) : newText;
                    if (finalText.length > 0) {
                        setText(finalText);
                        const num = parseFloat(finalText);
                        if (!isNaN(num)) onChange(clamp(num, min, max));
                        setSelectedIdx(prev => Math.min(prev, finalText.length - 1));
                    }
                }
            }
            return;
        }
        // Tab — commit and leave (don't trap focus)
        if (e.key === 'Tab') {
            onCommit();
            return;
        }
    };

    return (
        <div
            ref={containerRef}
            className={styles.digitEditor}
            tabIndex={0}
            onKeyDown={handleKeyDown}
            onBlur={onCommit}
        >
            {chars.map((ch, i) => (
                <span
                    key={i}
                    className={`${styles.digit} ${i === selectedIdx ? styles.digitSelected : ''} ${ch === '.' ? styles.digitDot : ''}`}
                    onMouseDown={(e) => {
                        e.preventDefault(); // prevent blur
                        if (ch !== '.' && ch !== '-') setSelectedIdx(i);
                    }}
                >
                    {ch}
                </span>
            ))}
        </div>
    );
}

export default function SliderControl({ label, icon, min, max, step, value: rawValue, defaultValue, ticks, onChange, onDragStart, onDragEnd }) {
    // Coerce to number — Trame state may send strings after state flush
    const value = typeof rawValue === 'number' ? rawValue : Number(rawValue) || 0;
    const hasDefaultTick = ticks?.length > 0;
    const tickPos = hasDefaultTick ? ((ticks[0] - min) / (max - min)) * 100 : null;
    const decimals = step < 0.01 ? 3 : step < 0.1 ? 2 : step < 1 ? 1 : 0;

    const [editing, setEditing] = useState(false);
    const [editText, setEditText] = useState('');
    const [selectedIdx, setSelectedIdx] = useState(0);
    // Display precision: starts at step-derived decimals, upgraded by user edits
    const [displayDecimals, setDisplayDecimals] = useState(decimals);
    const activeDecimals = Math.max(decimals, displayDecimals);

    const handleReset = (e) => {
        e.stopPropagation();
        if (defaultValue !== undefined) {
            onChange(defaultValue);
            setDisplayDecimals(decimals); // reset precision on reset
        }
    };

    const startEdit = useCallback(() => {
        const text = value?.toFixed(activeDecimals) ?? '0';
        setEditText(text);
        setSelectedIdx(text.length - 1);
        setEditing(true);
    }, [value, activeDecimals]);

    const commitEdit = useCallback(() => {
        setEditing(false);
        const num = parseFloat(editText);
        if (!isNaN(num)) {
            onChange(clamp(num, min, max));
            // Persist the user's precision for display
            const dotIdx = editText.indexOf('.');
            const prec = dotIdx === -1 ? 0 : editText.length - dotIdx - 1;
            setDisplayDecimals(prec);
        }
    }, [editText, min, max, onChange]);

    const cancelEdit = useCallback(() => {
        setEditing(false);
    }, []);

    return (
        <Slider
            className={styles.wrapper}
            minValue={min}
            maxValue={max}
            step={step}
            value={value}
            onChange={(val) => {
                onDragStart?.();
                onChange(val);
            }}
            onChangeEnd={() => onDragEnd?.()}
        >
            <div className={styles.header}>
                {icon && <span className={styles.icon}>{getIcon(icon)}</span>}
                <span className={styles.label}>{label}</span>
                <SliderOutput className={styles.output}>
                    {() =>
                        editing ? (
                            <DigitEditor
                                text={editText}
                                setText={setEditText}
                                selectedIdx={selectedIdx}
                                setSelectedIdx={setSelectedIdx}
                                onCommit={commitEdit}
                                onCancel={cancelEdit}
                                onChange={onChange}
                                min={min}
                                max={max}
                            />
                        ) : (
                            <span className={styles.outputValue} onClick={startEdit} data-tooltip="Click to edit">
                                {value?.toFixed(activeDecimals)}
                            </span>
                        )
                    }
                </SliderOutput>
            </div>
            <SliderTrack className={styles.track}>
                {({ state }) => {
                    const pct = state.getThumbPercent(0) * 100;
                    return (
                        <>
                            <div className={styles.trackFill} style={{ width: `${pct}%` }} />
                            {hasDefaultTick && (
                                <div
                                    className={styles.tick}
                                    style={{
                                        left: `${tickPos}%`,
                                        transform: `translateX(-${tickPos}%)`,
                                    }}
                                    onClick={handleReset}
                                    data-tooltip={`Reset to ${ticks[0]}`}
                                />
                            )}
                            <SliderThumb className={styles.thumb} />
                        </>
                    );
                }}
            </SliderTrack>
        </Slider>
    );
}

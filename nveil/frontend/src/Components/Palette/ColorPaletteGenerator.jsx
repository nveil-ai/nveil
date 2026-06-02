// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useTranslation } from 'react-i18next';
import { useState, useMemo, useCallback, useRef, useEffect } from 'react';
import {
  ColorPicker,
  ColorArea,
  ColorThumb,
  ColorSlider,
  SliderTrack,
  parseColor,
  Button,
  Dialog,
  DialogTrigger,
  Popover,
  Slider,
  SliderOutput,
  SliderThumb,
  Label,
} from 'react-aria-components';
import { TbLine } from 'react-icons/tb';
import { BiHorizontalRight } from 'react-icons/bi';
import styles from './ColorPaletteGenerator.module.css';

// ============================================================================
// Color Utility Functions (inlined)
// ============================================================================

/**
 * Converts a hex color string to RGB object
 */
function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : { r: 0, g: 0, b: 0 };
}

/**
 * Converts RGB to hex
 */
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(x => {
    const hex = Math.round(Math.max(0, Math.min(255, x))).toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

/**
 * Interpolates between two colors
 */
function interpolateColor(color1, color2, t, mode) {
  if (mode === 'constant') {
    return t < 1 ? color1 : color2;
  }
  const rgb1 = hexToRgb(color1);
  const rgb2 = hexToRgb(color2);
  return rgbToHex(
    rgb1.r + (rgb2.r - rgb1.r) * t,
    rgb1.g + (rgb2.g - rgb1.g) * t,
    rgb1.b + (rgb2.b - rgb1.b) * t
  );
}

/**
 * Gets the color at a specific position in the palette
 */
function getColorAtPosition(breaks, position) {
  if (breaks.length === 0) return '#000000';
  if (breaks.length === 1) return breaks[0].color;

  position = Math.max(0, Math.min(1, position));

  let lower = breaks[0];
  let upper = breaks[breaks.length - 1];

  for (let i = 0; i < breaks.length - 1; i++) {
    if (position >= breaks[i].position && position <= breaks[i + 1].position) {
      lower = breaks[i];
      upper = breaks[i + 1];
      break;
    }
  }

  if (position <= lower.position) return lower.color;
  if (position >= upper.position) return upper.color;

  const t = (position - lower.position) / (upper.position - lower.position);
  return interpolateColor(lower.color, upper.color, t, lower.interpolation);
}

/**
 * Generates a discretized palette
 */
function generateDiscretePalette(breaks, count) {
  if (count <= 0) return [];
  if (count === 1) return [getColorAtPosition(breaks, 0.5)];

  const colors = [];
  for (let i = 0; i < count; i++) {
    const position = i / (count - 1);
    colors.push(getColorAtPosition(breaks, position));
  }
  return colors;
}

/**
 * Generates unique ID
 */
function generateId() {
  return Math.random().toString(36).substring(2, 11);
}

/**
 * Derive the anchor token (the persisted form) for a break.
 * Endpoints with no lock → "min"/"max". Locked → numeric-literal string.
 * Otherwise → "NN%".
 */
function computeAnchor(brk, isFirst, isLast) {
  if (brk.locked && brk.lockedValue !== undefined && brk.lockedValue !== null) {
    return String(brk.lockedValue);
  }
  if (isFirst) return 'min';
  if (isLast) return 'max';
  return `${Math.round(brk.position * 100)}%`;
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * Inline editable value component
 */
function EditableValue({ value, onChange, className, min, max }) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [tempValue, setTempValue] = useState(value.toString());
  const inputRef = useRef(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.select();
    }
  }, [editing]);

  const handleSubmit = () => {
    const num = parseFloat(tempValue);
    if (!isNaN(num)) {
      let finalValue = num;
      if (min !== undefined) finalValue = Math.max(min, finalValue);
      if (max !== undefined) finalValue = Math.min(max, finalValue);
      onChange(finalValue);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={tempValue}
        onChange={(e) => setTempValue(e.target.value)}
        onBlur={handleSubmit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit();
          if (e.key === 'Escape') setEditing(false);
        }}
        className={className}
      />
    );
  }

  let displayValue = '?';
  if (typeof value === 'number' && !isNaN(value)) {
    displayValue = value.toFixed(2);
  } else if (value !== undefined && value !== null) {
    displayValue = value.toString();
  }
  return (
    <span
      onClick={() => { setTempValue((typeof value === 'number' && !isNaN(value)) ? value.toString() : ''); setEditing(true); }}
      className={className}
      data-tooltip={t('chat.colorPalette.editValue', 'Click to edit')}
    >
      {displayValue}
    </span>
  );
}

/**
 * Editable break position value.
 * Displays: "min"/"max" (endpoints, unlocked), "NN%" (interior, unlocked),
 * or a numeric literal (locked). Typing a number auto-locks the break
 * to that absolute value.
 */
function EditableBreakValue({
  brk, isFirst, isLast, minValue, maxValue,
  onLockAtValue, onToggleLock, style,
}) {
  const [editing, setEditing] = useState(false);
  const [tempValue, setTempValue] = useState('');
  const inputRef = useRef(null);

  const actualValue = minValue + brk.position * (maxValue - minValue);
  const anchorLabel = computeAnchor(brk, isFirst, isLast);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.select();
    }
  }, [editing]);

  const handleSubmit = () => {
    const num = parseFloat(tempValue);
    if (!isNaN(num)) {
      onLockAtValue(num);
    }
    setEditing(false);
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type="text"
        value={tempValue}
        onChange={(e) => setTempValue(e.target.value)}
        onBlur={handleSubmit}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === 'Enter') handleSubmit();
          if (e.key === 'Escape') setEditing(false);
        }}
        onClick={(e) => e.stopPropagation()}
        className={styles.breakValueInput}
        style={style}
      />
    );
  }

  const display = brk.locked
    ? Number(brk.lockedValue).toFixed(2)
    : anchorLabel;
  const lockedTitle = brk.locked
    ? 'Locked to absolute value — click 🔒 to unlock'
    : 'Click 🔒 to lock at current value';

  return (
    <span className={styles.breakValue} style={style}>
      <span
        onClick={(e) => {
          e.stopPropagation();
          setTempValue(actualValue.toFixed(2));
          setEditing(true);
        }}
        data-tooltip="Click to edit — typing a number locks to that value"
        style={{ cursor: 'text' }}
      >
        {display}
      </span>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onToggleLock(); }}
        className={styles.lockToggle}
        data-tooltip={lockedTitle}
        style={{ marginLeft: 2, background: 'transparent', border: 'none', cursor: 'pointer', padding: 0 }}
      >
        {brk.locked ? '🔒' : '🔓'}
      </button>
    </span>
  );
}

/**
 * Color Picker Popover for break handles
 */
function BreakColorPicker({ color, onChange, onDelete, children, isOpen, onOpenChange }) {
  const [colorValue, setColorValue] = useState(() => {
    try { return parseColor(color); }
    catch { return parseColor('#ffffff'); }
  });

  const handleChange = useCallback((newColor) => {
    setColorValue(newColor);
    onChange(newColor.toString('hex'));
  }, [onChange]);

  useEffect(() => {
    try {
      const parsed = parseColor(color);
      setColorValue(current => {
        if (parsed.toString('hex') !== current.toString('hex')) {
          return parsed;
        }
        return current;
      });
    } catch { /* ignore */ }
  }, [color]);

  // Stop click propagation on the entire popover to prevent adding breaks
  const handlePopoverClick = useCallback((e) => {
    e.stopPropagation();
  }, []);

  return (
    <ColorPicker value={colorValue} onChange={handleChange}>
      <DialogTrigger isOpen={isOpen} onOpenChange={onOpenChange}>
        {children}
        <Popover
          placement="top"
          className={styles.breakPopover}
          onClick={handlePopoverClick}
          onMouseDown={handlePopoverClick}
        >
          <Dialog className={styles.breakDialog}>
            <ColorArea
              colorSpace="hsb"
              xChannel="saturation"
              yChannel="brightness"
              className={styles.miniColorArea}
            >
              <ColorThumb className={styles.miniColorThumb} />
            </ColorArea>
            <ColorSlider colorSpace="hsb" channel="hue" className={styles.miniColorSlider}>
              <SliderTrack className={styles.miniSliderTrack}>
                <ColorThumb className={styles.miniColorThumb} />
              </SliderTrack>
            </ColorSlider>
            {onDelete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete();
                  onOpenChange?.(false);
                }}
                className={styles.deleteBreakBtn}
              >
                {useTranslation().t('chat.colorPalette.removeBreak', 'Remove Break')}
              </button>
            )}
          </Dialog>
        </Popover>
      </DialogTrigger>
    </ColorPicker>
  );
}

/**
 * Interpolation mode toggle between two breaks - positioned above the bar
 */
function InterpolationToggle({ mode, onChange, style }) {
  const { t } = useTranslation();
  return (
    <button
      className={styles.interpolationToggle}
      style={style}
      onClick={(e) => {
        e.stopPropagation();
        onChange(mode === 'linear' ? 'constant' : 'linear');
      }}
      data-tooltip={mode === 'linear'
        ? t('chat.colorPalette.linearInterpolation', 'Linear interpolation (click to toggle)')
        : t('chat.colorPalette.constantInterpolation', 'Constant interpolation (click to toggle)')}
    >
      {mode === 'linear' ? <TbLine size={12} /> : <BiHorizontalRight size={12} />}
    </button>
  );
}

/**
 * Interactive Color Bar with draggable break handles
 */
function InteractiveColorBar({
  breaks,
  minValue,
  maxValue,
  colorCount,
  onBreakUpdate,
  onBreakAdd,
  onBreakRemove,
  onBreakLockToggle,
  onBreakLockAtValue,
  onMinChange,
  onMaxChange,
}) {
  const barRef = useRef(null);
  const [draggingId, setDraggingId] = useState(null);
  const [hovering, setHovering] = useState(false);
  const [hoverPosition, setHoverPosition] = useState(null);
  const [openPickerId, setOpenPickerId] = useState(null);

  // Generate discretized gradient
  const gradientStyle = useMemo(() => {
    if (breaks.length === 0) return { background: '#000000' };

    const sortedBreaks = [...breaks].sort((a, b) => a.position - b.position);
    const colors = generateDiscretePalette(sortedBreaks, colorCount);

    if (colors.length === 1) return { background: colors[0] };

    const stops = colors.map((color, i) => {
      const startPct = (i / colors.length) * 100;
      const endPct = ((i + 1) / colors.length) * 100;
      return `${color} ${startPct.toFixed(2)}% ${endPct.toFixed(2)}%`;
    });

    return { background: `linear-gradient(to right, ${stops.join(', ')})` };
  }, [breaks, colorCount]);

  const getPositionFromEvent = useCallback((e) => {
    if (!barRef.current) return 0;
    const rect = barRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    return Math.max(0, Math.min(1, x / rect.width));
  }, []);

  // Handle drag
  useEffect(() => {
    if (!draggingId) return;

    const handleMouseMove = (e) => {
      const position = getPositionFromEvent(e);
      const brk = breaks.find((b) => b.id === draggingId);
      const updates = { position };
      if (brk?.locked) {
        updates.lockedValue = minValue + position * (maxValue - minValue);
      }
      onBreakUpdate(draggingId, updates);
    };

    const handleMouseUp = () => {
      setDraggingId(null);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [draggingId, getPositionFromEvent, onBreakUpdate, breaks, minValue, maxValue]);

  // Handle bar click to add new break - only if not clicking on handles/toggles/popovers
  const handleBarClick = useCallback((e) => {
    // Don't add break if clicking on interactive elements
    if (e.target.closest(`.${styles.breakHandle}`) ||
      e.target.closest(`.${styles.interpolationToggle}`) ||
      e.target.closest(`.${styles.breakPopover}`) ||
      e.target.closest(`.${styles.breakValue}`) ||
      e.target.closest(`.${styles.breakValueInput}`) ||
      e.target.closest('[data-react-aria-popover]')) {
      return;
    }

    const position = getPositionFromEvent(e);
    const sortedBreaks = [...breaks].sort((a, b) => a.position - b.position);
    const color = getColorAtPosition(sortedBreaks, position);
    onBreakAdd(position, color);
  }, [breaks, getPositionFromEvent, onBreakAdd]);

  const handleMouseMove = useCallback((e) => {
    if (draggingId) return;
    if (e.target.closest(`.${styles.breakHandle}`) ||
      e.target.closest(`.${styles.interpolationToggle}`) ||
      e.target.closest(`.${styles.breakValue}`) ||
      e.target.closest(`.${styles.breakValueInput}`)) {
      setHoverPosition(null);
      return;
    }
    const position = getPositionFromEvent(e);
    setHoverPosition(position);
  }, [draggingId, getPositionFromEvent]);

  const sortedBreaks = useMemo(() =>
    [...breaks].sort((a, b) => a.position - b.position),
    [breaks]);

  return (
    <div className={styles.colorBarContainer}>
      <EditableValue
        value={minValue}
        onChange={onMinChange}
        className={styles.edgeValue}
      />

      <div className={styles.colorBarWrapper}>
        {/* Interpolation toggles ABOVE the bar */}
        <div className={styles.interpolationRow}>
          {sortedBreaks.slice(0, -1).map((brk, i) => {
            const nextBrk = sortedBreaks[i + 1];
            const midPosition = (brk.position + nextBrk.position) / 2;
            return (
              <InterpolationToggle
                key={`interp-${brk.id}`}
                mode={brk.interpolation}
                onChange={(mode) => onBreakUpdate(brk.id, { interpolation: mode })}
                style={{ left: `${midPosition * 100}%` }}
              />
            );
          })}
        </div>

        <div
          ref={barRef}
          className={styles.colorBar}
          style={gradientStyle}
          onClick={handleBarClick}
          onMouseEnter={() => setHovering(true)}
          onMouseLeave={() => { setHovering(false); setHoverPosition(null); }}
          onMouseMove={handleMouseMove}
        >
          {/* Hover indicator for adding breaks */}
          {hovering && hoverPosition !== null && !draggingId && openPickerId === null && (
            <div
              className={styles.addBreakIndicator}
              style={{ left: `${hoverPosition * 100}%` }}
            >
              <span className={styles.addBreakPlus}>+</span>
            </div>
          )}

          {/* Break handles */}
          {sortedBreaks.map((brk) => (
            <BreakColorPicker
              key={brk.id}
              color={brk.color}
              onChange={(color) => onBreakUpdate(brk.id, { color })}
              onDelete={breaks.length > 1 ? () => onBreakRemove(brk.id) : null}
              isOpen={openPickerId === brk.id}
              onOpenChange={(open) => setOpenPickerId(open ? brk.id : null)}
            >
              <Button
                className={styles.breakHandle}
                style={{
                  left: `${brk.position * 100}%`,
                  backgroundColor: brk.color,
                }}
                onMouseDown={(e) => {
                  e.stopPropagation();
                  setDraggingId(brk.id);
                }}
                aria-label={`Color break at ${(minValue + brk.position * (maxValue - minValue)).toFixed(2)}`}
              />
            </BreakColorPicker>
          ))}
        </div>

        {/* Editable value indicators below bar */}
        <div className={styles.breakValues}>
          {sortedBreaks.map((brk, idx) => (
            <EditableBreakValue
              key={brk.id}
              brk={brk}
              isFirst={idx === 0}
              isLast={idx === sortedBreaks.length - 1}
              minValue={minValue}
              maxValue={maxValue}
              onToggleLock={() => onBreakLockToggle(brk.id)}
              onLockAtValue={(val) => onBreakLockAtValue(brk.id, val)}
              style={{ left: `${brk.position * 100}%` }}
            />
          ))}
        </div>
      </div>

      <EditableValue
        value={maxValue}
        onChange={onMaxChange}
        className={styles.edgeValue}
      />
    </div>
  );
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * Compact Color Palette Generator Component
 * 
 * @param {Object} props
 * @param {number} [props.defaultMinValue=0] - Default minimum value
 * @param {number} [props.defaultMaxValue=1] - Default maximum value  
 * @param {Array} [props.defaultBreaks] - Default color breaks
 * @param {number} [props.defaultColorCount=10] - Default number of discrete colors
 * @param {'hex'|'rgb'} [props.format='hex'] - Output color format (not user-facing)
 * @param {Function} [props.onChange] - Callback when palette changes
 */
export function ColorPaletteGenerator({
  defaultMinValue = 0,
  defaultMaxValue = 1,
  defaultBreaks,
  defaultColorCount = 10,
  format = 'hex',
  onChange,
}) {
  const [minValue, setMinValue] = useState(defaultMinValue);
  const [maxValue, setMaxValue] = useState(defaultMaxValue);
  const [colorCount, setColorCount] = useState(defaultColorCount);

  const [colorBreaks, setColorBreaks] = useState(() => {
    if (defaultBreaks && defaultBreaks.length > 0) {
      return defaultBreaks.map(b => ({
        locked: false,
        lockedValue: null,
        ...b,
        id: b.id || generateId(),
      }));
    }
    return [
      { id: generateId(), position: 0, color: '#0000ff', interpolation: 'linear', locked: false, lockedValue: null },
      { id: generateId(), position: 0.5, color: '#ffffff', interpolation: 'linear', locked: false, lockedValue: null },
      { id: generateId(), position: 1, color: '#ff0000', interpolation: 'linear', locked: false, lockedValue: null },
    ];
  });

  const sortedBreaks = useMemo(() =>
    [...colorBreaks].sort((a, b) => a.position - b.position),
    [colorBreaks]);

  const discretePalette = useMemo(() =>
    generateDiscretePalette(sortedBreaks, colorCount),
    [sortedBreaks, colorCount]);

  const formattedColors = useMemo(() => {
    if (format === 'rgb') {
      return discretePalette.map(hex => {
        const rgb = hexToRgb(hex);
        return `rgb(${rgb.r}, ${rgb.g}, ${rgb.b})`;
      });
    }
    return discretePalette;
  }, [discretePalette, format]);

  // Persist-shape breaks: each carries its anchor token alongside the
  // internal position, so the parent can save either form without
  // re-deriving it.
  const anchoredBreaks = useMemo(() =>
    sortedBreaks.map((brk, idx) => ({
      ...brk,
      anchor: computeAnchor(brk, idx === 0, idx === sortedBreaks.length - 1),
    })),
    [sortedBreaks]);

  // Notify parent
  useEffect(() => {
    onChange?.(formattedColors, anchoredBreaks, minValue, maxValue);
  }, [formattedColors, anchoredBreaks, minValue, maxValue, onChange]);

  const handleBreakUpdate = useCallback((id, updates) => {
    setColorBreaks(prev => prev.map(brk =>
      brk.id === id ? { ...brk, ...updates } : brk
    ));
  }, []);

  const handleBreakAdd = useCallback((position, color) => {
    setColorBreaks(prev => {
      const newBreaks = [...prev, {
        id: generateId(),
        position,
        color,
        interpolation: 'linear',
        locked: false,
        lockedValue: null,
      }];
      const minColors = newBreaks.length;
      if (colorCount < minColors) {
        setColorCount(minColors);
      }
      return newBreaks;
    });
  }, [colorCount]);

  const handleBreakLockToggle = useCallback((id) => {
    setColorBreaks(prev => prev.map(brk => {
      if (brk.id !== id) return brk;
      if (brk.locked) {
        return { ...brk, locked: false, lockedValue: null };
      }
      const actualValue = minValue + brk.position * (maxValue - minValue);
      return { ...brk, locked: true, lockedValue: actualValue };
    }));
  }, [minValue, maxValue]);

  const handleBreakLockAtValue = useCallback((id, value) => {
    setColorBreaks(prev => prev.map(brk => {
      if (brk.id !== id) return brk;
      const span = maxValue - minValue || 1;
      const newPosition = Math.max(0, Math.min(1, (value - minValue) / span));
      return { ...brk, locked: true, lockedValue: value, position: newPosition };
    }));
  }, [minValue, maxValue]);

  const handleBreakRemove = useCallback((id) => {
    setColorBreaks(prev => {
      const filtered = prev.filter(brk => brk.id !== id);
      return filtered;
    });
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(formattedColors));
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, [formattedColors]);

  const { t } = useTranslation();
  return (
    <div className={styles.container}>
      <InteractiveColorBar
        breaks={colorBreaks}
        minValue={minValue}
        maxValue={maxValue}
        colorCount={colorCount}
        onBreakUpdate={handleBreakUpdate}
        onBreakAdd={handleBreakAdd}
        onBreakRemove={handleBreakRemove}
        onBreakLockToggle={handleBreakLockToggle}
        onBreakLockAtValue={handleBreakLockAtValue}
        onMinChange={setMinValue}
        onMaxChange={setMaxValue}
      />

      <div className={styles.controls}>
        <Slider
          minValue={1}
          maxValue={255}
          value={colorCount}
          onChange={setColorCount}
          className={styles.colorSlider}
        >
          <div className={styles.sliderHeader}>
            <Label className={styles.sliderLabel}>{t('chat.colorPalette.colors', 'Colors')}</Label>
            <SliderOutput className={styles.sliderOutput} />
          </div>
          <SliderTrack className={styles.sliderTrack}>
            <SliderThumb className={styles.sliderThumb} />
          </SliderTrack>
        </Slider>

        <button onClick={handleCopy} className={styles.copyBtn} data-tooltip={t('chat.colorPalette.copyToClipboard', 'Copy colors to clipboard')}>
          {t('chat.colorPalette.copy', 'Copy')}
        </button>
      </div>
    </div>
  );
}

export default ColorPaletteGenerator;

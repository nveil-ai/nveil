// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MdExpandMore } from 'react-icons/md';
import { getIcon } from '../iconMap';
import SliderControl from './SliderControl';
import styles from './ClippingControl.module.css';

const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const poly = (pts) => pts.map(p => p.join(',')).join(' ');

// ---------------------------------------------------------------------------
// Axis schema — isometric cube with axis-aligned cut planes
//
// Each cut is perpendicular to its axis and slices across two faces:
//   X → right face (vertical) + top face
//   Y → left face (vertical) + top face
//   Z → right face (horizontal) + left face (horizontal)
//
// The KEPT (visible) region is colored on each affected face.
// ---------------------------------------------------------------------------

function AxisSchema({ x, y, z }) {
    const cx = 80, cy = 62;
    const s = 26;
    const ix = s * 0.866, iy = s * 0.5;

    // Isometric cube vertices
    const top    = [cx, cy - s * 2];
    const tLeft  = [cx - ix, cy - s * 2 + iy];
    const tRight = [cx + ix, cy - s * 2 + iy];
    const mid    = [cx, cy - s * 2 + 2 * iy];
    const bLeft  = [cx - ix, cy - iy];
    const bRight = [cx + ix, cy - iy];
    const bot    = [cx, cy];

    const rightFace = [bot, bRight, tRight, mid];
    const leftFace  = [bot, bLeft, tLeft, mid];
    const topFace   = [mid, tLeft, top, tRight];

    const keptPolygons = [];

    // --- Per-axis kept ranges [lo, hi] as fractions 0–1 along each axis ---
    const xFrac = Math.abs(x);
    const yFrac = Math.abs(y);
    const zFrac = Math.abs(z);
    // Each range: what fraction of each axis is kept
    const xRange = xFrac < 0.005 ? [0, 1] : x > 0 ? [xFrac, 1] : [0, 1 - xFrac];
    const yRange = yFrac < 0.005 ? [0, 1] : y > 0 ? [0, 1 - yFrac] : [yFrac, 1];
    const zRange = zFrac < 0.005 ? [0, 1] : z > 0 ? [0, 1 - zFrac] : [zFrac, 1];

    // Helper: get a point on a face parameterized by (u, v) in [0,1]²
    // Right face: u=X(bot→bRight), v=Z(bot→mid)
    const rightPt = (u, v) => lerp(lerp(bot, bRight, u), lerp(mid, tRight, u), v);
    // Left face: u=Y(bot→bLeft), v=Z(bot→mid)
    const leftPt = (u, v) => lerp(lerp(bot, bLeft, u), lerp(mid, tLeft, u), v);
    // Top face: u=X(mid→tRight), v=Y(mid→tLeft)
    const topPt = (u, v) => lerp(lerp(mid, tRight, u), lerp(tLeft, top, u), v);

    // --- Individual colored fills per axis (unchanged behavior) ---

    if (zFrac > 0.005) {
        const t = z > 0 ? 1 - zFrac : zFrac;
        const gR = lerp(bot, mid, t), hR = lerp(bRight, tRight, t), iL = lerp(bLeft, tLeft, t);
        if (z > 0) {
            keptPolygons.push({ pts: [bot, bRight, hR, gR], color: '#3b82f6' });
            keptPolygons.push({ pts: [bot, bLeft, iL, gR], color: '#3b82f6' });
        } else {
            keptPolygons.push({ pts: [gR, hR, tRight, mid], color: '#3b82f6' });
            keptPolygons.push({ pts: [gR, iL, tLeft, mid], color: '#3b82f6' });
            keptPolygons.push({ pts: topFace, color: '#3b82f6' });
        }
    }

    if (xFrac > 0.005) {
        const t = x > 0 ? xFrac : 1 - xFrac;
        const a = lerp(bot, bRight, t), b = lerp(mid, tRight, t), c = lerp(tLeft, top, t);
        if (x > 0) {
            keptPolygons.push({ pts: [a, bRight, tRight, b], color: '#ef4444' });
            keptPolygons.push({ pts: [b, c, top, tRight], color: '#ef4444' });
        } else {
            keptPolygons.push({ pts: [bot, a, b, mid], color: '#ef4444' });
            keptPolygons.push({ pts: [mid, tLeft, c, b], color: '#ef4444' });
            keptPolygons.push({ pts: leftFace, color: '#ef4444' });
        }
    }

    if (yFrac > 0.005) {
        const t = y > 0 ? 1 - yFrac : yFrac;
        const a = lerp(bot, bLeft, t), b = lerp(mid, tLeft, t), c = lerp(tRight, top, t);
        if (y > 0) {
            keptPolygons.push({ pts: [bot, a, b, mid], color: '#22c55e' });
            keptPolygons.push({ pts: [mid, b, c, tRight], color: '#22c55e' });
            keptPolygons.push({ pts: rightFace, color: '#22c55e' });
        } else {
            keptPolygons.push({ pts: [a, bLeft, tLeft, b], color: '#22c55e' });
            keptPolygons.push({ pts: [b, tLeft, top, c], color: '#22c55e' });
        }
    }

    // --- White overlay: combined kept surface on each external face ---
    // Only drawn when at least one axis is active. The intersection of
    // all axis ranges on each face shows the actual visible surface.
    const anyActive = xFrac > 0.005 || yFrac > 0.005 || zFrac > 0.005;
    const surfacePolygons = [];

    if (anyActive) {
        // Right face (Y=0): clipped by X (u) and Z (v).
        // Hidden when Y negative (keep high-Y excludes Y=0 face).
        const rShow = !(y < 0 && yFrac > 0.005);
        if (rShow && xRange[1] > xRange[0] + 0.001 && zRange[1] > zRange[0] + 0.001) {
            surfacePolygons.push([
                rightPt(xRange[0], zRange[0]),
                rightPt(xRange[1], zRange[0]),
                rightPt(xRange[1], zRange[1]),
                rightPt(xRange[0], zRange[1]),
            ]);
        }

        // Left face (X=0): clipped by Y (u) and Z (v).
        // Hidden when X positive (keep high-X excludes X=0 face).
        const lShow = !(x > 0 && xFrac > 0.005);
        if (lShow && yRange[1] > yRange[0] + 0.001 && zRange[1] > zRange[0] + 0.001) {
            surfacePolygons.push([
                leftPt(yRange[0], zRange[0]),
                leftPt(yRange[1], zRange[0]),
                leftPt(yRange[1], zRange[1]),
                leftPt(yRange[0], zRange[1]),
            ]);
        }

        // Top face (Z=1): clipped by X (u) and Y (v).
        // Hidden when Z positive (keep low-Z excludes Z=1 face).
        const tShow = !(z > 0 && zFrac > 0.005);
        if (tShow && xRange[1] > xRange[0] + 0.001 && yRange[1] > yRange[0] + 0.001) {
            surfacePolygons.push([
                topPt(xRange[0], yRange[0]),
                topPt(xRange[1], yRange[0]),
                topPt(xRange[1], yRange[1]),
                topPt(xRange[0], yRange[1]),
            ]);
        }
    }

    return (
        <svg className={styles.schema} viewBox="0 0 160 80">
            {/* Face outlines */}
            <polygon points={poly(rightFace)} fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
            <polygon points={poly(leftFace)}  fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
            <polygon points={poly(topFace)}   fill="rgba(255,255,255,0.03)" stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />

            {/* Kept regions — per-axis colored fills */}
            {keptPolygons.map(({ pts, color }, i) => (
                <polygon key={i} points={poly(pts)} fill={color} fillOpacity={0.25}
                    stroke={color} strokeWidth={1} strokeOpacity={0.5} />
            ))}

            {/* Combined kept surface — white overlay on each visible external face */}
            {surfacePolygons.map((pts, i) => (
                <polygon key={`sf-${i}`} points={poly(pts)}
                    fill="rgba(255,255,255,0.2)" stroke="rgba(255,255,255,0.6)"
                    strokeWidth={1.2} />
            ))}

            {/* Axis labels */}
            <text x={bRight[0] + 6} y={bRight[1] + 4} fill="#ef4444" fontSize="8" fontWeight="600">X</text>
            <text x={bLeft[0] - 12} y={bLeft[1] + 4} fill="#22c55e" fontSize="8" fontWeight="600">Y</text>
            <text x={top[0] + 4} y={top[1] - 2} fill="#3b82f6" fontSize="8" fontWeight="600">Z</text>
        </svg>
    );
}

// ---------------------------------------------------------------------------
// Camera schema — eye → frustum → isometric 3D cube (square proportions)
//
// The cube is square, fits inside the frustum, and all visible faces
// of the kept region are filled blue.
// ---------------------------------------------------------------------------

function CameraSchema({ depth }) {
    const eyeX = 10, eyeY = 40;

    // Square isometric cube — edge length determines proportions
    const edge = 32;
    const dxIso = edge * 0.35;  // isometric X offset for depth
    const dyIso = edge * -0.25; // isometric Y offset for depth

    // Position the cube so it's centered vertically and sits in the right portion
    const cubeLeft = 62;
    const cubeTop = eyeY - edge / 2;
    const cubeBot = eyeY + edge / 2;
    const cubeRight = cubeLeft + edge;

    // Front face (rectangle, facing camera)
    const fTL = [cubeLeft, cubeTop];
    const fTR = [cubeRight, cubeTop];
    const fBL = [cubeLeft, cubeBot];
    const fBR = [cubeRight, cubeBot];

    // Back face (offset by isometric depth)
    const bTL = [cubeLeft + dxIso, cubeTop + dyIso];
    const bTR = [cubeRight + dxIso, cubeTop + dyIso];
    const bBL = [cubeLeft + dxIso, cubeBot + dyIso];
    const bBR = [cubeRight + dxIso, cubeBot + dyIso];

    // Near face corners (camera side) — frustum connects to these
    // fTL, fTR, fBL, fBR are the 4 corners of the front face

    // Cut plane position: depth 0→1 maps to cubeLeft→cubeRight
    const cutX = cubeLeft + depth * edge;
    const cutXBack = cubeLeft + dxIso + depth * edge;

    return (
        <svg className={styles.schema} viewBox="0 0 160 80">
            <defs>
                <marker id="cam-arr" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
                    <path d="M0,0 L6,2 L0,4" fill="rgba(255,255,255,0.25)" />
                </marker>
            </defs>

            {/* Frustum lines — from eye to the 4 left-face corners (camera side) */}
            <line x1={eyeX} y1={eyeY} x2={fTL[0]} y2={fTL[1]}
                stroke="rgba(27,144,186,0.2)" strokeWidth={0.8} />
            <line x1={eyeX} y1={eyeY} x2={fBL[0]} y2={fBL[1]}
                stroke="rgba(27,144,186,0.2)" strokeWidth={0.8} />
            <line x1={eyeX} y1={eyeY} x2={bTL[0]} y2={bTL[1]}
                stroke="rgba(27,144,186,0.2)" strokeWidth={0.8} />
            <line x1={eyeX} y1={eyeY} x2={bBL[0]} y2={bBL[1]}
                stroke="rgba(27,144,186,0.2)" strokeWidth={0.8} />

            {/* Back face edges */}
            <line x1={bTL[0]} y1={bTL[1]} x2={bTR[0]} y2={bTR[1]} stroke="rgba(255,255,255,0.08)" strokeWidth={0.7} />
            <line x1={bTR[0]} y1={bTR[1]} x2={bBR[0]} y2={bBR[1]} stroke="rgba(255,255,255,0.08)" strokeWidth={0.7} />
            <line x1={bBL[0]} y1={bBL[1]} x2={bBR[0]} y2={bBR[1]} stroke="rgba(255,255,255,0.08)" strokeWidth={0.7} />
            <line x1={bTL[0]} y1={bTL[1]} x2={bBL[0]} y2={bBL[1]} stroke="rgba(255,255,255,0.08)" strokeWidth={0.7} />

            {/* Connecting edges front→back */}
            <line x1={fTL[0]} y1={fTL[1]} x2={bTL[0]} y2={bTL[1]} stroke="rgba(255,255,255,0.1)" strokeWidth={0.7} />
            <line x1={fTR[0]} y1={fTR[1]} x2={bTR[0]} y2={bTR[1]} stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />
            <line x1={fBL[0]} y1={fBL[1]} x2={bBL[0]} y2={bBL[1]} stroke="rgba(255,255,255,0.1)" strokeWidth={0.7} />
            <line x1={fBR[0]} y1={fBR[1]} x2={bBR[0]} y2={bBR[1]} stroke="rgba(255,255,255,0.12)" strokeWidth={0.8} />

            {/* Kept region — all visible faces from cutX to far side */}
            {depth < 0.99 && (
                <>
                    {/* Front face (facing camera): cutX → cubeRight */}
                    <rect x={cutX} y={cubeTop} width={cubeRight - cutX} height={edge}
                        fill="#1b90ba" fillOpacity={0.2} />
                    {/* Top face: parallelogram from cut line to far edge */}
                    <polygon points={poly([
                        [cutX, cubeTop], [cubeRight, cubeTop],
                        [cubeRight + dxIso, cubeTop + dyIso], [cutXBack, cubeTop + dyIso],
                    ])} fill="#1b90ba" fillOpacity={0.15} />
                    {/* Right side face: cubeRight face fully visible */}
                    <polygon points={poly([
                        fTR, fBR, bBR, bTR,
                    ])} fill="#1b90ba" fillOpacity={0.12} />
                    {/* Bottom face: parallelogram */}
                    <polygon points={poly([
                        [cutX, cubeBot], [cubeRight, cubeBot],
                        [cubeRight + dxIso, cubeBot + dyIso], [cutXBack, cubeBot + dyIso],
                    ])} fill="#1b90ba" fillOpacity={0.1} />
                    {/* Back face: cutXBack → far edge */}
                    <rect x={cutXBack} y={cubeTop + dyIso} width={cubeRight + dxIso - cutXBack} height={edge}
                        fill="#1b90ba" fillOpacity={0.08} />
                </>
            )}
            {depth <= 0.01 && (
                <>
                    <rect x={cubeLeft} y={cubeTop} width={edge} height={edge}
                        fill="#1b90ba" fillOpacity={0.1} />
                    <polygon points={poly([fTL, fTR, bTR, bTL])}
                        fill="#1b90ba" fillOpacity={0.08} />
                    <polygon points={poly([fTR, fBR, bBR, bTR])}
                        fill="#1b90ba" fillOpacity={0.06} />
                </>
            )}

            {/* Front face outline */}
            <rect x={cubeLeft} y={cubeTop} width={edge} height={edge}
                fill="none" stroke="rgba(255,255,255,0.2)" strokeWidth={1} />

            {/* Cut plane lines */}
            {depth > 0.01 && depth < 0.99 && (
                <>
                    <line x1={cutX} y1={cubeTop - 1} x2={cutX} y2={cubeBot + 1}
                        stroke="#1b90ba" strokeWidth={2} strokeOpacity={0.9} />
                    <line x1={cutX} y1={cubeTop} x2={cutXBack} y2={cubeTop + dyIso}
                        stroke="#1b90ba" strokeWidth={1.5} strokeOpacity={0.6} />
                    <line x1={cutX} y1={cubeBot} x2={cutXBack} y2={cubeBot + dyIso}
                        stroke="#1b90ba" strokeWidth={1} strokeOpacity={0.4} />
                </>
            )}

            {/* Depth arrow */}
            {depth > 0.05 && (
                <line x1={cubeLeft + 2} y1={cubeBot + 6} x2={cutX - 2} y2={cubeBot + 6}
                    stroke="rgba(255,255,255,0.2)" strokeWidth={0.8}
                    markerEnd="url(#cam-arr)" />
            )}

            {/* Eye */}
            <circle cx={eyeX} cy={eyeY} r={5}
                fill="none" stroke="rgba(27,144,186,0.4)" strokeWidth={1} />
            <circle cx={eyeX} cy={eyeY} r={2}
                fill="#1b90ba" fillOpacity={0.7} />
        </svg>
    );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ClippingControl({ label, getValue, setValue }) {
    const { t } = useTranslation();
    const [isOpen, setIsOpen] = useState(false);

    const mode = getValue('space.clipping.mode') ?? 'axis';
    const clipX = getValue('space.clipping.xPlane') ?? 0;
    const clipY = getValue('space.clipping.yPlane') ?? 0;
    const clipZ = getValue('space.clipping.zPlane') ?? 0;
    const depth = getValue('space.clipping.cameraDepth') ?? 0;

    const tLabel = (key) => t('widgets.' + key, key);

    return (
        <div className={styles.group}>
            <button
                className={styles.header}
                onClick={() => setIsOpen(!isOpen)}
                type="button"
            >
                <span className={styles.headerIcon}>{getIcon('clip')}</span>
                <span className={styles.headerLabel}>{tLabel('ClippingPlanes')}</span>
                <MdExpandMore className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} />
            </button>
            {isOpen && (
                <div className={styles.content}>
                    <div className={styles.toggle}>
                        <button
                            className={`${styles.tab} ${mode === 'axis' ? styles.tabActive : ''}`}
                            onClick={() => setValue('space.clipping.mode', 'axis')}
                            type="button"
                        >
                            {tLabel('AxisAligned')}
                        </button>
                        <button
                            className={`${styles.tab} ${mode === 'camera' ? styles.tabActive : ''}`}
                            onClick={() => setValue('space.clipping.mode', 'camera')}
                            type="button"
                        >
                            {tLabel('CameraAligned')}
                        </button>
                    </div>

                    <div className={styles.schemaWrap}>
                        {mode === 'axis'
                            ? <AxisSchema x={clipX} y={clipY} z={clipZ} />
                            : <CameraSchema depth={depth} />
                        }
                    </div>

                    <div className={styles.sliders}>
                        {mode === 'axis' ? (
                            <>
                                <SliderControl
                                    label="X" icon="clip-x"
                                    min={-1} max={1} step={0.01}
                                    value={clipX} defaultValue={0}
                                    ticks={[0]}
                                    onChange={(v) => setValue('space.clipping.xPlane', v)}
                                />
                                <SliderControl
                                    label="Y" icon="clip-y"
                                    min={-1} max={1} step={0.01}
                                    value={clipY} defaultValue={0}
                                    ticks={[0]}
                                    onChange={(v) => setValue('space.clipping.yPlane', v)}
                                />
                                <SliderControl
                                    label="Z" icon="clip-z"
                                    min={-1} max={1} step={0.01}
                                    value={clipZ} defaultValue={0}
                                    ticks={[0]}
                                    onChange={(v) => setValue('space.clipping.zPlane', v)}
                                />
                            </>
                        ) : (
                            <SliderControl
                                label={tLabel('CameraClipDepth')} icon="clip-camera"
                                min={0} max={1} step={0.01}
                                value={depth} defaultValue={0}
                                ticks={[0]}
                                onChange={(v) => setValue('space.clipping.cameraDepth', v)}
                            />
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

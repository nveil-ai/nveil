// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { MdClose, MdLock, MdFileDownload } from 'react-icons/md';
import styles from './ExportDialog.module.css';

const FORMATS = [
    { value: 'jpeg', label: 'JPEG', mime: 'image/jpeg' },
    { value: 'png', label: 'PNG', mime: 'image/png' },
    { value: 'svg', label: 'SVG', mime: 'image/svg+xml' },
    { value: 'pdf', label: 'PDF', mime: 'application/pdf' },
];

export default function ExportDialog({ communicatorRef, onClose }) {
    const { t } = useTranslation();
    const [format, setFormat] = useState('jpeg');
    const [transparent, setTransparent] = useState(false);
    const [width, setWidth] = useState(1200);
    const [height, setHeight] = useState(1200);
    const [scale, setScale] = useState(1);
    const [viewerType, setViewerType] = useState(null);
    const [disabledFormats, setDisabledFormats] = useState({});
    const [exporting, setExporting] = useState(false);

    // Read current state from trame on mount
    useEffect(() => {
        const comm = communicatorRef?.current;
        if (!comm?.state) return;
        comm.state.get().then((s) => {
            if (!s) return;
            if (s.export_extension) setFormat(s.export_extension);
            if (s.export_transparent != null) setTransparent(s.export_transparent);
            if (s.export_width) setWidth(s.export_width);
            if (s.export_height) setHeight(s.export_height);
            if (s.export_scale) setScale(s.export_scale);
            if (s.current_viewer_type) setViewerType(s.current_viewer_type);
            setDisabledFormats({
                png: s.export_png_disabled,
                jpeg: s.export_jpeg_disabled,
                svg: s.export_svg_disabled,
                pdf: s.export_pdf_disabled,
            });
        }).catch(() => {});
    }, [communicatorRef]);

    // SVG and PDF export are only available for ECharts (server-side
    // Playwright render). VTK, graph, and HTML viewers don't support
    // those formats.
    const supportsVectorExport = viewerType === 'echarts' || viewerType == null;

    const handleExport = () => {
        const comm = communicatorRef?.current;
        if (!comm?.state) return;

        setExporting(true);

        // Push export settings to trame state
        comm.state.update({
            export_extension: format,
            export_transparent: transparent,
            export_width: width,
            export_height: height,
            export_scale: scale,
        });

        // Request the trame iframe to execute the download trigger
        setTimeout(() => {
            const iframe = document.getElementById('trame-iframe');
            if (iframe?.contentWindow) {
                iframe.contentWindow.postMessage(
                    { type: 'trigger-export-download', format },
                    '*'
                );
            }
            setTimeout(() => setExporting(false), 2000);
        }, 200);
    };

    return (
        <div className={styles.overlay} onClick={onClose}>
            <div className={styles.dialog} onClick={e => e.stopPropagation()}>
                <div className={styles.header}>
                    <MdFileDownload size={18} className={styles.headerIcon} />
                    <span className={styles.title}>{t('widgets.ExportImage')}</span>
                    <button className={styles.closeBtn} onClick={onClose}>
                        <MdClose size={16} />
                    </button>
                </div>

                <div className={styles.body}>
                    {/* Format selection */}
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>{t('widgets.FileExtension')}</label>
                        <div className={styles.formatGrid}>
                            {FORMATS.map(f => {
                                const disabled = disabledFormats[f.value];
                                const unavailable = !supportsVectorExport && (f.value === 'svg' || f.value === 'pdf');
                                return (
                                    <button
                                        key={f.value}
                                        className={`${styles.formatBtn} ${format === f.value ? styles.formatActive : ''} ${(disabled || unavailable) ? styles.formatDisabled : ''}`}
                                        onClick={() => !disabled && !unavailable && setFormat(f.value)}
                                        data-tooltip={disabled ? t('widgets.ExportRequiresLicense') : unavailable ? 'Plotly only' : f.label}
                                    >
                                        {f.label}
                                        {disabled && <MdLock size={12} className={styles.lockIcon} />}
                                    </button>
                                );
                            })}
                        </div>
                    </div>

                    {/* Transparent (PNG only) */}
                    {format === 'png' && (
                        <div className={styles.field}>
                            <label className={styles.checkboxLabel}>
                                <input
                                    type="checkbox"
                                    checked={transparent}
                                    onChange={e => setTransparent(e.target.checked)}
                                    className={styles.checkbox}
                                />
                                {t('widgets.TransparentBackground')}
                            </label>
                        </div>
                    )}

                    {/* Dimensions */}
                    <div className={styles.field}>
                        <label className={styles.fieldLabel}>{t('widgets.ImageSize')}</label>
                        <div className={styles.sizeRow}>
                            <div className={styles.sizeInput}>
                                <span className={styles.sizeLabel}>{t('widgets.Width')}</span>
                                <input
                                    type="number"
                                    value={width}
                                    onChange={e => setWidth(parseInt(e.target.value) || 0)}
                                    className={styles.numInput}
                                    min={100}
                                    max={8000}
                                />
                            </div>
                            <span className={styles.sizeSep}>&times;</span>
                            <div className={styles.sizeInput}>
                                <span className={styles.sizeLabel}>{t('widgets.Height')}</span>
                                <input
                                    type="number"
                                    value={height}
                                    onChange={e => setHeight(parseInt(e.target.value) || 0)}
                                    className={styles.numInput}
                                    min={100}
                                    max={8000}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Scale — ECharts Playwright export supports device scale factor */}
                    {supportsVectorExport && (
                        <div className={styles.field}>
                            <label className={styles.fieldLabel}>{t('widgets.Scale')}</label>
                            <input
                                type="range"
                                min={0.1}
                                max={10}
                                step={0.1}
                                value={scale}
                                onChange={e => setScale(parseFloat(e.target.value))}
                                className={styles.rangeInput}
                            />
                            <span className={styles.rangeValue}>{scale.toFixed(1)}x</span>
                        </div>
                    )}
                </div>

                <button
                    className={styles.exportBtn}
                    onClick={handleExport}
                    disabled={exporting || disabledFormats[format]}
                >
                    {exporting ? t('widgets.Exporting') : t('widgets.Save')}
                </button>
            </div>
        </div>
    );
}

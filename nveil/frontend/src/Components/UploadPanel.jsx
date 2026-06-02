// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, {
    useState, useRef, useCallback, useEffect,
    forwardRef, useImperativeHandle,
} from 'react';
import styles from './UploadPanel.module.css';
import SequenceOptions from './SequenceOptions';
import { MdAdd, MdWarning } from 'react-icons/md';
import { TbFileTypeCsv, TbFileTypeXls } from 'react-icons/tb';
import { FaFileMedical, FaFile } from 'react-icons/fa';
import { BsCloudUpload } from 'react-icons/bs';

const MAX_URLS = 5;

export const getFileIcon = (file) => {
    const ext = (file.name || file.original_name || '').toLowerCase();
    const dotExt = ext.substring(ext.lastIndexOf('.'));
    if (dotExt === ".csv") return <TbFileTypeCsv style={{ fontSize: '1.1em', color: "#fff" }} />;
    if ([".xlsx", ".xls", ".ods", ".xlsm"].includes(dotExt)) return <TbFileTypeXls style={{ fontSize: '1.1em', color: "#22c55e" }} />;
    if ([".mhd", ".zraw"].includes(dotExt)) return <FaFileMedical style={{ fontSize: '1.1em', color: "#fff" }} />;
    return <FaFile style={{ fontSize: '1em', color: "#6859a3" }} />;
};

export const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${sizes[i]}`;
};

const UploadPanel = forwardRef(function UploadPanel({
    pendingFiles,
    setPendingFiles,
    allowedExtensions = null,
    maxFileSize = null,
    t,
    secureRequest,
    isSubmitting = false,
    fileInputRef,
}, ref) {
    const [dropActive, setDropActive] = useState(false);
    const [urlInputs, setUrlInputs] = useState([{ url: '', label: '' }]);

    // Connector state
    const [availableConnectors, setAvailableConnectors] = useState([]);
    const [selectedConnector, setSelectedConnector] = useState(null);
    const [allNative, setAllNative] = useState(true);

    // Sequence state
    const [isSequence, setIsSequence] = useState(false);
    const [sequenceTimeMode, setSequenceTimeMode] = useState('index');
    const [sequenceDeltaValue, setSequenceDeltaValue] = useState(1);
    const [sequenceDeltaUnit, setSequenceDeltaUnit] = useState('s');

    const dropZoneRef = useRef(null);

    // ── Expose getSubmitData() and reset() to parent ──

    useImperativeHandle(ref, () => ({
        getSubmitData() {
            const urls = urlInputs.filter(u => u.url.trim());
            const sequenceMeta = isSequence
                ? { timeMode: sequenceTimeMode, deltaValue: sequenceDeltaValue, deltaUnit: sequenceDeltaUnit }
                : null;
            return {
                urls,
                connector: selectedConnector,
                sequenceMeta,
            };
        },
        reset() {
            setUrlInputs([{ url: '', label: '' }]);
            setAvailableConnectors([]);
            setSelectedConnector(null);
            setAllNative(true);
            setIsSequence(false);
            setSequenceTimeMode('index');
            setSequenceDeltaValue(1);
            setSequenceDeltaUnit('s');
        },
    }), [urlInputs, selectedConnector, isSequence, sequenceTimeMode, sequenceDeltaValue, sequenceDeltaUnit]);

    // ── Detect connectors when pending files change ──

    useEffect(() => {
        if (pendingFiles.length === 0) {
            setAvailableConnectors([]);
            setSelectedConnector(null);
            setAllNative(true);
            return;
        }
        const extensions = [...new Set(
            pendingFiles.map(f => {
                const dot = f.name.lastIndexOf('.');
                return dot >= 0 ? f.name.substring(dot).toLowerCase() : '';
            }).filter(Boolean)
        )];
        secureRequest(`/server/connectors/match?extensions=${extensions.join(',')}`)
            .then(res => res.ok ? res.json() : null)
            .then(data => {
                if (!data) return;
                setAvailableConnectors(data.connectors || []);
                setAllNative(data.all_native);
                // Auto-select connector
                const allDcm = pendingFiles.length > 1 && extensions.length === 1 && extensions[0] === '.dcm';
                const dicomConnector = (data.connectors || []).find(c => c.id === 'dicom');
                let autoSelected = null;
                if (allDcm && dicomConnector) {
                    autoSelected = 'dicom';
                } else if (!data.all_native && data.connectors?.length === 1) {
                    autoSelected = data.connectors[0].id;
                }
                setSelectedConnector(autoSelected);

                // When a connector is selected with multiple files, auto-enable Sequence: Auto
                if (autoSelected && autoSelected !== 'dicom' && pendingFiles.length > 1) {
                    setIsSequence(true);
                    setSequenceTimeMode('auto');
                }
            })
            .catch(() => {});
    }, [pendingFiles, secureRequest]);

    // ── Drop zone handlers ──

    const handleDropZoneDragOver = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setDropActive(true);
    }, []);

    const handleDropZoneDragLeave = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setDropActive(false);
    }, []);

    const handleDropZoneDrop = useCallback((e) => {
        e.preventDefault();
        e.stopPropagation();
        setDropActive(false);
        if (e.dataTransfer?.files?.length > 0) {
            let files = Array.from(e.dataTransfer.files);
            // Optional validation
            if (allowedExtensions || maxFileSize) {
                files = files.filter(file => {
                    const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
                    const extOk = !allowedExtensions || allowedExtensions.includes(ext);
                    const sizeOk = !maxFileSize || file.size <= maxFileSize;
                    return extOk && sizeOk;
                });
            }
            if (files.length > 0) {
                setPendingFiles(prev => [...prev, ...files]);
            }
        }
    }, [setPendingFiles, allowedExtensions, maxFileSize]);

    const handleRemoveFile = useCallback((idx) => {
        setPendingFiles(prev => prev.filter((_, i) => i !== idx));
    }, [setPendingFiles]);

    // ── URL input management ──

    const handleUrlChange = (index, field, value) => {
        setUrlInputs(prev => prev.map((item, i) =>
            i === index ? { ...item, [field]: value } : item
        ));
    };

    const addUrlInput = () => {
        if (urlInputs.length < MAX_URLS) {
            setUrlInputs(prev => [...prev, { url: '', label: '' }]);
        }
    };

    const removeUrlInput = (index) => {
        setUrlInputs(prev => prev.filter((_, i) => i !== index));
    };

    return (
        <div className={styles.uploadRow}>
            {/* File upload section */}
            <div className={styles.section} style={{ flex: 1 }}>
                <div className={styles.sectionHeader}>{t("chat.fileUploadTitle")}</div>
                <div
                    ref={dropZoneRef}
                    className={`${styles.dropZone} ${dropActive ? styles.dropZoneActive : ''}`}
                    onClick={() => fileInputRef?.current?.click()}
                    onDragOver={handleDropZoneDragOver}
                    onDragLeave={handleDropZoneDragLeave}
                    onDrop={handleDropZoneDrop}
                >
                    <BsCloudUpload className={styles.dropZoneIcon} />
                    <span className={styles.dropZoneText}>{t("chat.dropOrBrowse")}</span>
                </div>
                {pendingFiles.length > 0 && (
                    <div className={styles.pendingFiles}>
                        {pendingFiles.map((file, idx) => (
                            <span key={file.name + idx} className={styles.fileBadge}>
                                {getFileIcon(file)}
                                <span className={styles.fileName}>{file.name}</span>
                                <button
                                    type="button"
                                    className={styles.removeFileBtn}
                                    onClick={(e) => { e.stopPropagation(); handleRemoveFile(idx); }}
                                    data-tooltip={t("chat.remove")}
                                    style={isSubmitting ? { display: 'none' } : undefined}
                                >
                                    &times;
                                </button>
                            </span>
                        ))}
                    </div>
                )}
                {/* Temporal sequence -- visible when uploading 2+ files */}
                {pendingFiles.length >= 2 && (
                    <SequenceOptions
                        isSequence={isSequence} setIsSequence={setIsSequence}
                        timeMode={sequenceTimeMode} setTimeMode={setSequenceTimeMode}
                        deltaValue={sequenceDeltaValue} setDeltaValue={setSequenceDeltaValue}
                        deltaUnit={sequenceDeltaUnit} setDeltaUnit={setSequenceDeltaUnit}
                        t={t}
                    />
                )}
                {/* Connector selector */}
                {availableConnectors.length > 0 && pendingFiles.length > 0 && (
                    <div className={styles.connectorSection}>
                        <div className={styles.connectorLabel}>{t("data.projectType", { defaultValue: "Project type" })}</div>
                        <div className={styles.connectorOptions}>
                            <button
                                className={`${styles.connectorBtn} ${!selectedConnector ? styles.connectorBtnActive : ''}`}
                                onClick={() => setSelectedConnector(null)}
                                disabled={!allNative}
                            >
                                Auto
                            </button>
                            {availableConnectors.map(c => (
                                <button
                                    key={c.id}
                                    className={`${styles.connectorBtn} ${selectedConnector === c.id ? styles.connectorBtnActive : ''}`}
                                    onClick={() => setSelectedConnector(c.id)}
                                    data-tooltip={c.description}
                                >
                                    {c.label}
                                </button>
                            ))}
                        </div>
                        {selectedConnector && (() => {
                            const conn = availableConnectors.find(c => c.id === selectedConnector);
                            if (!conn) return null;
                            const pendingExts = new Set(pendingFiles.map(f => {
                                const dot = f.name.lastIndexOf('.');
                                return dot >= 0 ? f.name.substring(dot).toLowerCase() : '';
                            }));
                            const missing = conn.required.filter(ext => !pendingExts.has(ext));
                            if (missing.length > 0) {
                                return (
                                    <div className={styles.connectorMissing}>
                                        <MdWarning style={{ flexShrink: 0 }} />
                                        <span>{t("data.connectorMissing", { files: missing.join(', '), defaultValue: `Please add: ${missing.join(', ')} file(s)` })}</span>
                                    </div>
                                );
                            }
                            return null;
                        })()}
                    </div>
                )}
            </div>

            {/* URL source section */}
            <div className={styles.section} style={{ flex: 1 }}>
                <div className={styles.sectionHeader}>{t("chat.urlSourceTitle")}</div>
                <div className={styles.urlList}>
                    {urlInputs.map((entry, idx) => (
                        <div key={idx} className={styles.urlRow}>
                            <input
                                type="url"
                                placeholder="https://example.com/data.csv"
                                value={entry.url}
                                onChange={e => handleUrlChange(idx, 'url', e.target.value)}
                                className={styles.inputField}
                            />
                            <div className={styles.urlLabelRow}>
                                <input
                                    type="text"
                                    placeholder={t("chat.urlLabelPlaceholder")}
                                    value={entry.label}
                                    onChange={e => handleUrlChange(idx, 'label', e.target.value)}
                                    className={styles.inputField}
                                />
                                {urlInputs.length > 1 && (
                                    <button
                                        type="button"
                                        className={styles.removeUrlBtn}
                                        onClick={() => removeUrlInput(idx)}
                                        data-tooltip={t("chat.remove")}
                                    >
                                        &times;
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}
                    {urlInputs.length < MAX_URLS && (
                        <button
                            type="button"
                            className={styles.addUrlBtn}
                            onClick={addUrlInput}
                        >
                            <MdAdd /> {t("chat.addUrl")}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
});

export default UploadPanel;

// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-FileContributor: Guillaume Franque
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../Auth/AuthContext';
import { queue } from '../App';
import SEO from '../Components/SEO';
import styles from './DataManager.module.css';
import {
    Cell, Column, Row, Table, TableBody, TableHeader,
    Checkbox,
} from 'react-aria-components';
import {
    MdCloudUpload, MdSearch, MdEdit, MdDelete,
    MdRefresh, MdStorage, MdArrowUpward, MdArrowDownward,
    MdClose, MdWarning, MdLink,
} from 'react-icons/md';
import { AiOutlineLoading3Quarters } from 'react-icons/ai';
import { IoClose } from 'react-icons/io5';
import useAllowedExtensions from '../hooks/useAllowedExtensions';
import UploadPanel, { formatBytes } from '../Components/UploadPanel';
import { buildIsoDuration } from '../Components/SequenceOptions';

function CheckboxIcon() {
    return (
        <div className="checkbox">
            <svg viewBox="0 0 18 18" aria-hidden="true">
                <polyline points="1 9 7 14 15 4" />
            </svg>
        </div>
    );
}

const FORMAT_ICON_CLASS = {
    csv: styles.fileIconCsv,
    xlsx: styles.fileIconXlsx, xls: styles.fileIconXlsx,
    ods: styles.fileIconXlsx, xlsm: styles.fileIconXlsx,
    json: styles.fileIconJson,
    mhd: styles.fileIconMhd, zraw: styles.fileIconMhd,
    png: styles.fileIconImage, jpg: styles.fileIconImage,
    jpeg: styles.fileIconImage, tiff: styles.fileIconImage,
    tif: styles.fileIconImage, bmp: styles.fileIconImage,
    webp: styles.fileIconImage, gif: styles.fileIconImage,
    xml: styles.fileIconOther, mat: styles.fileIconOther,
};


function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function DataManager() {
    const { t } = useTranslation();
    const { secureRequest, isAuthenticated, isGuest } = useAuth();
    const { accept: allowedExtensions } = useAllowedExtensions();

    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [uploading, setUploading] = useState(false);
    const [search, setSearch] = useState('');
    const [dragging, setDragging] = useState(false);
    const [sortDescriptor, setSortDescriptor] = useState({ column: 'created_at', direction: 'descending' });
    const [selectedKeys, setSelectedKeys] = useState(new Set());

    // Delete confirmation modal
    const [deleteModal, setDeleteModal] = useState({ open: false, fileIds: [], fileNames: [] });

    // Upload modal
    const [uploadModalOpen, setUploadModalOpen] = useState(false);
    const [pendingFiles, setPendingFiles] = useState([]);

    const fileInputRef = useRef(null);
    const dragCounter = useRef(0);
    const uploadPanelRef = useRef(null);

    // ── Fetch files ──

    const fetchFiles = useCallback(async () => {
        if (!isAuthenticated) return;
        try {
            const res = await secureRequest('/server/data/list');
            if (res.ok) {
                const data = await res.json();
                setFiles(data.files || []);
            }
        } catch (e) {
            console.error('Failed to fetch files:', e);
        }
        setLoading(false);
    }, [isAuthenticated, secureRequest]);

    useEffect(() => { fetchFiles(); }, [fetchFiles]);

    // Poll while any file is still processing
    useEffect(() => {
        const hasProcessing = files.some(f => f.processing_status === 'processing');
        if (!hasProcessing) return;
        const timer = setInterval(() => fetchFiles(), 4000);
        return () => clearInterval(timer);
    }, [files, fetchFiles]);


    // ── Upload ──

    const handleUploadSubmit = async () => {
        const { urls, connector, sequenceMeta } = uploadPanelRef.current?.getSubmitData() || {};
        const hasFiles = pendingFiles.length > 0;
        const hasUrls = urls?.length > 0;
        if (!hasFiles && !hasUrls) return;

        setUploadModalOpen(false);
        setUploading(true);

        try {
            if (hasFiles) {
                const formData = new FormData();
                for (const f of pendingFiles) formData.append('files', f);
                if (connector) formData.append('connector', connector);
                if (sequenceMeta) {
                    formData.append('sequence_time_mode', sequenceMeta.timeMode);
                    if (sequenceMeta.timeMode === 'time_based') {
                        formData.append('sequence_time_delta', buildIsoDuration(sequenceMeta.timeMode, sequenceMeta.deltaValue, sequenceMeta.deltaUnit));
                    }
                }
                await secureRequest('/server/data/upload', {
                    method: 'POST',
                    body: formData,
                });
                setPendingFiles([]);
            }
            if (hasUrls) {
                await secureRequest('/server/data/upload-url', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ urls }),
                });
            }
        } catch (e) {
            console.error('Upload failed:', e);
        }

        uploadPanelRef.current?.reset();
        await fetchFiles();
        setUploading(false);
    };

    // ── Drag & drop (window-level → opens modal with dropped files) ──

    const uploadModalOpenRef = useRef(false);
    useEffect(() => { uploadModalOpenRef.current = uploadModalOpen; }, [uploadModalOpen]);

    useEffect(() => {
        const onEnter = (e) => {
            e.preventDefault();
            if (uploadModalOpenRef.current) return; // modal handles its own drops
            dragCounter.current++;
            setDragging(true);
        };
        const onLeave = (e) => {
            e.preventDefault();
            if (uploadModalOpenRef.current) return;
            dragCounter.current--;
            if (dragCounter.current <= 0) { setDragging(false); dragCounter.current = 0; }
        };
        const onOver = (e) => e.preventDefault();
        const onDrop = (e) => {
            e.preventDefault();
            setDragging(false);
            dragCounter.current = 0;
            if (uploadModalOpenRef.current) return; // modal handles its own drops
            if (e.dataTransfer?.files?.length > 0) {
                setPendingFiles(Array.from(e.dataTransfer.files));
                setUploadModalOpen(true);
            }
        };

        window.addEventListener('dragenter', onEnter);
        window.addEventListener('dragleave', onLeave);
        window.addEventListener('dragover', onOver);
        window.addEventListener('drop', onDrop);
        return () => {
            window.removeEventListener('dragenter', onEnter);
            window.removeEventListener('dragleave', onLeave);
            window.removeEventListener('dragover', onOver);
            window.removeEventListener('drop', onDrop);
        };
    }, [isGuest]); // eslint-disable-line react-hooks/exhaustive-deps

    // ── Rename ──

    const [renameModal, setRenameModal] = useState({ open: false, fileId: null, name: '' });
    const renameInputRef = useRef(null);

    const openRenameModal = (file) => {
        setRenameModal({ open: true, fileId: file.id, name: file.display_name || file.original_name });
    };

    const commitRename = async () => {
        const { fileId, name } = renameModal;
        if (!fileId || !name.trim()) { setRenameModal({ open: false, fileId: null, name: '' }); return; }
        try {
            await secureRequest(`/server/data/${fileId}/rename`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ display_name: name.trim() }),
            });
            await fetchFiles();
        } catch (e) { console.error(e); }
        setRenameModal({ open: false, fileId: null, name: '' });
    };

    useEffect(() => {
        if (renameModal.open && renameInputRef.current) {
            renameInputRef.current.focus();
            renameInputRef.current.select();
        }
    }, [renameModal.open]);

    // ── Delete ──

    const requestDelete = (fileId) => {
        const file = files.find(f => f.id === fileId);
        setDeleteModal({
            open: true,
            fileIds: [fileId],
            fileNames: [file?.display_name || file?.original_name || fileId],
        });
    };

    const requestBulkDelete = () => {
        if (selectedKeys !== 'all' && selectedKeys.size === 0) return;
        const ids = selectedKeys === 'all' ? sortedFiles.map(f => f.id) : [...selectedKeys];
        const names = ids.map(id => {
            const file = files.find(f => f.id === id);
            return file?.display_name || file?.original_name || id;
        });
        setDeleteModal({ open: true, fileIds: ids, fileNames: names });
    };

    const confirmDelete = async () => {
        const { fileIds, fileNames } = deleteModal;
        setDeleteModal({ open: false, fileIds: [], fileNames: [] });
        let totalRoomsAffected = 0;
        for (const id of fileIds) {
            try {
                const resp = await secureRequest(`/server/data/${id}`, { method: 'DELETE' });
                if (resp.ok) {
                    const body = await resp.json();
                    totalRoomsAffected += body.rooms_affected || 0;
                }
            } catch (e) { console.error(e); }
        }
        if (totalRoomsAffected > 0) {
            queue.add(
                { title: t('data.deletedLinkedWarning', { count: totalRoomsAffected }) },
                { timeout: 6000 },
            );
        }
        setSelectedKeys(new Set());
        await fetchFiles();
    };

    // ── Re-upload ──

    const handleReupload = async (fileId) => {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = allowedExtensions;
        input.onchange = async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setUploading(true);
            const formData = new FormData();
            formData.append('file', file);
            try {
                await secureRequest(`/server/data/${fileId}/reupload`, {
                    method: 'POST',
                    body: formData,
                });
                await fetchFiles();
            } catch (err) { console.error(err); }
            setUploading(false);
        };
        input.click();
    };

    // ── Refetch URL-sourced file ──

    const handleRefetch = async (fileId) => {
        setUploading(true);
        try {
            await secureRequest(`/server/data/${fileId}/refetch`, {
                method: 'POST',
            });
            await fetchFiles();
        } catch (err) { console.error(err); }
        setUploading(false);
    };

    // ── Filter + sort ──

    const sortedFiles = useMemo(() => {
        let result = files;

        if (search) {
            const q = search.toLowerCase();
            result = result.filter((f) => {
                const name = (f.display_name || f.original_name || '').toLowerCase();
                return name.includes(q) || (f.format || '').toLowerCase().includes(q);
            });
        }

        if (sortDescriptor?.column) {
            result = [...result].sort((a, b) => {
                let av, bv;
                const col = sortDescriptor.column;
                if (col === 'name') {
                    av = (a.display_name || a.original_name || '').toLowerCase();
                    bv = (b.display_name || b.original_name || '').toLowerCase();
                } else if (col === 'size_bytes') {
                    av = a.size_bytes || 0;
                    bv = b.size_bytes || 0;
                } else if (col === 'room_count') {
                    av = a.room_count || 0;
                    bv = b.room_count || 0;
                } else {
                    av = a[col] || '';
                    bv = b[col] || '';
                }
                let cmp = av < bv ? -1 : av > bv ? 1 : 0;
                if (sortDescriptor.direction === 'descending') cmp *= -1;
                return cmp;
            });
        }

        return result;
    }, [files, search, sortDescriptor]);

    const columns = [
        { id: 'name', label: t('data.fileName'), isRowHeader: true, allowsSorting: true },
        { id: 'format', label: t('data.format'), allowsSorting: true },
        { id: 'size_bytes', label: t('data.size'), allowsSorting: true },
        { id: 'created_at', label: t('data.uploaded'), allowsSorting: true },
        { id: 'room_count', label: t('data.rooms'), allowsSorting: true },
        { id: 'actions', label: t('data.actions'), allowsSorting: false },
    ];

    // ── Render ──

    const hasSelection = selectedKeys === 'all' || selectedKeys.size > 0;
    const selectionCount = selectedKeys === 'all' ? sortedFiles.length : selectedKeys.size;

    return (
        <>
            <SEO title={t('data.title')} description={t('data.description')} />

            {dragging && (
                <div className={styles.dropOverlay}>
                    <div className={styles.dropZone}>
                        <MdCloudUpload className={styles.dropZoneIcon} />
                        <span className={styles.dropZoneText}>{t('data.dropzone')}</span>
                    </div>
                </div>
            )}

            <main className={styles.page}>
                <div className={styles.backdrop}>
                    {/* Header */}
                    <div className={styles.header}>
                        <div className={styles.headerLeft}>
                            <MdStorage className={styles.headerIcon} />
                            <div>
                                <h1 className={styles.title}>{t('data.title')}</h1>
                                <p className={styles.subtitle}>{t('data.description')}</p>
                            </div>
                        </div>
                        <div className={styles.headerActions}>
                            {hasSelection && (
                                <>
                                    <button
                                        className={styles.clearBtn}
                                        onClick={() => setSelectedKeys(new Set())}
                                    >
                                        <MdClose />
                                        {t('data.clearSelection')} ({selectionCount})
                                    </button>
                                    <button
                                        className={`${styles.uploadBtn} ${styles.deleteBtn}`}
                                        onClick={requestBulkDelete}
                                    >
                                        <MdDelete />
                                        {t('data.delete')}
                                    </button>
                                </>
                            )}
                            <div className={styles.searchWrap}>
                                <MdSearch className={styles.searchIcon} />
                                <input
                                    className={styles.searchInput}
                                    type="text"
                                    placeholder={t('data.searchFiles')}
                                    value={search}
                                    onChange={(e) => setSearch(e.target.value)}
                                />
                            </div>
                            <button
                                className={styles.uploadBtn}
                                onClick={() => { setPendingFiles([]); setUploadModalOpen(true); }}
                                disabled={isGuest}
                            >
                                <MdCloudUpload />
                                {t('data.uploadFiles')}
                            </button>
                            <input
                                ref={fileInputRef}
                                className={styles.hiddenInput}
                                type="file"
                                multiple
                                accept={allowedExtensions}
                                onChange={(e) => {
                                    const newFiles = Array.from(e.target.files);
                                    setPendingFiles(prev => [...prev, ...newFiles]);
                                    e.target.value = '';
                                }}
                            />
                        </div>
                    </div>

                    {/* Upload progress */}
                    {uploading && (
                        <div className={styles.uploadingBar}>
                            <div className={styles.spinner} />
                            <span className={styles.uploadingText}>{t('data.uploadFiles')}...</span>
                        </div>
                    )}

                    {/* Content */}
                    {loading ? (
                        <div className={styles.loading}>
                            <div className={styles.loadingPulse} />
                            <div className={styles.loadingPulse} />
                            <div className={styles.loadingPulse} />
                        </div>
                    ) : sortedFiles.length === 0 && !search ? (
                        <div className={styles.emptyState}>
                            <div className={styles.emptyIcon}><MdStorage /></div>
                            <h2 className={styles.emptyTitle}>{t('data.noFiles')}</h2>
                            <p className={styles.emptyHint}>{t('data.noFilesHint')}</p>
                            <div
                                className={styles.inlineDropZone}
                                onClick={() => { setPendingFiles([]); setUploadModalOpen(true); }}
                            >
                                <MdCloudUpload style={{ fontSize: '1.6rem', color: '#666' }} />
                                <span style={{ color: '#666', fontSize: '0.85rem' }}>{t('data.dropzone')}</span>
                            </div>
                        </div>
                    ) : (
                        <div className={styles.tableWrap}>
                            <Table
                                aria-label={t('data.title')}
                                sortDescriptor={sortDescriptor}
                                onSortChange={setSortDescriptor}
                                selectionMode="multiple"
                                selectionBehavior="replace"
                                selectedKeys={selectedKeys}
                                onSelectionChange={setSelectedKeys}
                                className={styles.table}
                            >
                                <TableHeader>
                                    <Column width={40} minWidth={40}>
                                        <Checkbox slot="selection"><CheckboxIcon /></Checkbox>
                                    </Column>
                                    {columns.map(col => (
                                        <Column
                                            key={col.id}
                                            id={col.id}
                                            isRowHeader={col.isRowHeader}
                                            allowsSorting={col.allowsSorting}
                                        >
                                            {({ allowsSorting, sortDirection }) => (
                                                <div className={col.id === 'actions' ? styles.colHeaderRight : styles.colHeader}>
                                                    <span>{col.label}</span>
                                                    {allowsSorting && sortDirection && (
                                                        <span className={styles.sortIndicator}>
                                                            {sortDirection === 'ascending'
                                                                ? <MdArrowUpward />
                                                                : <MdArrowDownward />
                                                            }
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </Column>
                                    ))}
                                </TableHeader>
                                <TableBody items={sortedFiles} renderEmptyState={() => (
                                    <div className={styles.noResults}>{t('data.noResults')}</div>
                                )}>
                                    {(file) => (
                                        <Row id={file.id}>
                                            <Cell>
                                                <Checkbox slot="selection"><CheckboxIcon /></Checkbox>
                                            </Cell>
                                            <Cell>
                                                <div className={styles.fileNameCell}>
                                                    <div className={`${styles.fileIcon} ${FORMAT_ICON_CLASS[file.format] || styles.fileIconOther}`}>
                                                        {file.format?.slice(0, 3) || '?'}
                                                    </div>
                                                    <div className={styles.fileNameBlock}>
                                                                <span className={styles.fileDisplayName}>
                                                                    {file.display_name || file.original_name}
                                                                </span>
                                                                {file.companion_files?.length > 0 && (
                                                                    <span className={styles.companionNames}>
                                                                        + {file.companion_files.join(', ')}
                                                                    </span>
                                                                )}
                                                                {file.display_name && file.display_name !== file.original_name && (
                                                                    <span className={styles.fileOriginalName}>{file.original_name}</span>
                                                                )}
                                                                {file.collection_time_mode && (
                                                                    <span className={styles.collectionBadge}>
                                                                        Sequence
                                                                    </span>
                                                                )}
                                                                {file.upload_source === 'url' && file.source_url && (
                                                                    <span className={styles.sourceUrl} title={file.source_url}>
                                                                        <MdLink className={styles.sourceUrlIcon} />
                                                                        {file.source_url}
                                                                    </span>
                                                                )}
                                                                {file.processing_status === 'processing' && (
                                                                    <span className={styles.processingBadge}>
                                                                        <AiOutlineLoading3Quarters className={styles.processingSpinner} />
                                                                        {t("data.processing")}
                                                                    </span>
                                                                )}
                                                                {file.processing_status === 'error' && (
                                                                    <span className={styles.errorBadge}>{t("data.processingError")}</span>
                                                                )}
                                                    </div>
                                                </div>
                                            </Cell>
                                            <Cell>
                                                <div className={styles.formatBadges}>
                                                    {(() => {
                                                        const counts = {};
                                                        counts[file.format] = 1;
                                                        for (const cf of (file.companion_files || [])) {
                                                            const ext = cf.split('.').pop()?.toLowerCase();
                                                            if (ext) counts[ext] = (counts[ext] || 0) + 1;
                                                        }
                                                        return Object.entries(counts).map(([ext, n]) => (
                                                            <span key={ext} className={styles.formatBadge}>
                                                                {ext}{n > 1 ? ` ×${n}` : ''}
                                                            </span>
                                                        ));
                                                    })()}
                                                </div>
                                            </Cell>
                                            <Cell>{formatBytes(file.size_bytes)}</Cell>
                                            <Cell>{formatDate(file.created_at)}</Cell>
                                            <Cell>
                                                <span className={`${styles.roomCount} ${file.room_count === 0 ? styles.roomCountZero : ''}`}>
                                                    {file.room_count}
                                                </span>
                                            </Cell>
                                            <Cell>
                                                <div className={styles.actions}>
                                                    <button className={styles.actionBtn} onClick={() => openRenameModal(file)} data-tooltip={t('data.rename')}>
                                                        <MdEdit />
                                                    </button>
                                                    {file.upload_source === 'url' ? (
                                                        <button className={styles.actionBtn} onClick={() => handleRefetch(file.id)} data-tooltip={t('data.refetch')}>
                                                            <MdRefresh />
                                                        </button>
                                                    ) : (
                                                        <button className={styles.actionBtn} onClick={() => handleReupload(file.id)} data-tooltip={t('data.reupload')}>
                                                            <MdRefresh />
                                                        </button>
                                                    )}
                                                    <button className={`${styles.actionBtn} ${styles.actionBtnDanger}`} onClick={() => requestDelete(file.id)} data-tooltip={t('data.delete')}>
                                                        <MdDelete />
                                                    </button>
                                                </div>
                                            </Cell>
                                        </Row>
                                    )}
                                </TableBody>
                            </Table>
                        </div>
                    )}
                </div>
            </main>

            {/* ── Rename modal ── */}
            {renameModal.open && (
                <div className={styles.modalOverlay} onClick={() => setRenameModal({ open: false, fileId: null, name: '' })}>
                    <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                        <div className={styles.modal}>
                            <div className={styles.modalHeader}>
                                <MdEdit style={{ color: '#1b90ba', fontSize: '1.2rem', flexShrink: 0 }} />
                                <span className={styles.modalTitle}>{t('data.rename')}</span>
                                <button className={styles.modalCloseBtn} onClick={() => setRenameModal({ open: false, fileId: null, name: '' })}>
                                    <IoClose />
                                </button>
                            </div>
                            <div className={styles.modalBody}>
                                <input
                                    ref={renameInputRef}
                                    className={styles.renameInput}
                                    value={renameModal.name}
                                    onChange={(e) => setRenameModal(prev => ({ ...prev, name: e.target.value }))}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') commitRename();
                                        if (e.key === 'Escape') setRenameModal({ open: false, fileId: null, name: '' });
                                    }}
                                />
                            </div>
                            <div className={styles.modalFooter}>
                                <button
                                    className={styles.modalCancelBtn}
                                    onClick={() => setRenameModal({ open: false, fileId: null, name: '' })}
                                >
                                    {t('cancel')}
                                </button>
                                <button
                                    className={styles.modalSubmitBtn}
                                    onClick={commitRename}
                                    disabled={!renameModal.name.trim()}
                                >
                                    {t('data.rename')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Delete confirmation modal ── */}
            {deleteModal.open && (
                <div className={styles.modalOverlay} onClick={() => setDeleteModal({ open: false, fileIds: [], fileNames: [] })}>
                    <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                        <div className={styles.modal}>
                            <div className={styles.modalHeader}>
                                <MdWarning className={styles.modalWarnIcon} />
                                <span className={styles.modalTitle}>{t('data.deleteConfirm')}</span>
                                <button className={styles.modalCloseBtn} onClick={() => setDeleteModal({ open: false, fileIds: [], fileNames: [] })}>
                                    <IoClose />
                                </button>
                            </div>
                            <div className={styles.modalBody}>
                                <div className={styles.deleteFileList}>
                                    {deleteModal.fileNames.map((name, i) => (
                                        <div key={i} className={styles.deleteFileItem}>{name}</div>
                                    ))}
                                </div>
                            </div>
                            <div className={styles.modalFooter}>
                                <button
                                    className={styles.modalCancelBtn}
                                    onClick={() => setDeleteModal({ open: false, fileIds: [], fileNames: [] })}
                                >
                                    {t('cancel')}
                                </button>
                                <button className={styles.modalDeleteBtn} onClick={confirmDelete}>
                                    <MdDelete />
                                    {t('data.delete')} ({deleteModal.fileIds.length})
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Upload modal ── */}
            {uploadModalOpen && (
                <div className={styles.modalOverlay} onClick={() => setUploadModalOpen(false)}>
                    <div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
                        <div className={styles.modal}>
                            <div className={styles.modalHeader}>
                                <span className={styles.modalTitle}>{t('data.uploadFiles')}</span>
                                <button className={styles.modalCloseBtn} onClick={() => setUploadModalOpen(false)}>
                                    <IoClose />
                                </button>
                            </div>
                            <div className={styles.modalBody}>
                                <UploadPanel
                                    ref={uploadPanelRef}
                                    pendingFiles={pendingFiles}
                                    setPendingFiles={setPendingFiles}
                                    t={t}
                                    secureRequest={secureRequest}
                                    isSubmitting={uploading}
                                    fileInputRef={fileInputRef}
                                />
                            </div>
                            <div className={styles.modalFooter}>
                                <button className={styles.modalCancelBtn} onClick={() => setUploadModalOpen(false)}>
                                    {t('cancel')}
                                </button>
                                <button
                                    className={styles.modalSubmitBtn}
                                    onClick={handleUploadSubmit}
                                    disabled={uploading}
                                >
                                    {uploading ? `${t('data.uploadFiles')}...` : t('data.uploadFiles')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}

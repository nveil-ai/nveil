// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, { useState, useRef, useCallback, useEffect } from 'react';
import styles from './DataSourcesModal.module.css';
import UploadPanel, { getFileIcon, formatBytes } from './UploadPanel';
import { IoClose } from 'react-icons/io5';
import { AiOutlineLoading3Quarters } from 'react-icons/ai';
import { useAuth } from '../Auth/AuthContext';
import { useRoom } from '../Room/RoomContext';
import useAllowedExtensions from '../hooks/useAllowedExtensions';

const maxSize = 1000 * 1024 * 1024;

export default function DataSourcesModal({
	isOpen,
	onClose,
	t,
	datasets,
	hasUrlSources,
	refreshInterval,
	pendingFiles,
	setPendingFiles,
	onUploadFiles,
	onApplyChanges,
	onLoadUrl,
	onRefresh,
	onSetRefreshInterval,
	fileInputRef,
	isUploading,
	isUrlLoading,
	isRefreshing,
	filesStatus,
	uploadError,
	clearUploadError,
	userFiles,
	fetchUserFiles,
}) {
	const { secureRequest } = useAuth();
	const { currentRoom } = useRoom();
	const { extensions: allowedExtensions } = useAllowedExtensions();
	const uploadPanelRef = useRef(null);

	// Your Files state
	const [isLegacyRoom, setIsLegacyRoom] = useState(false);

	// Pending link/unlink changes (tracked locally, applied on submit)
	const [pendingLinks, setPendingLinks] = useState(new Set());
	const [pendingUnlinks, setPendingUnlinks] = useState(new Set());
	const [isApplying, setIsApplying] = useState(false);

	const roomId = currentRoom?.id;

	// Snapshot of initial linked state when modal opens
	const initialLinkedRef = useRef(new Set());

	// Reset modal state + snapshot linked files when modal opens
	useEffect(() => {
		if (!isOpen) return;
		fetchUserFiles();
		setPendingLinks(new Set());
		setPendingUnlinks(new Set());
		uploadPanelRef.current?.reset();
		if (clearUploadError) clearUploadError();
		// Check workspace version
		fetch('/server/files/get_metadata?metadata_name=workspace_version', { credentials: 'include' })
			.then(r => r.ok ? r.json() : {})
			.then(data => {
				const version = data?.workspace_version;
				setIsLegacyRoom(version === "" || (typeof version === "number" && version < 2));
			})
			.catch(() => setIsLegacyRoom(false));
	}, [isOpen]); // eslint-disable-line react-hooks/exhaustive-deps

	// Snapshot initial linked state whenever userFiles change while modal is open
	useEffect(() => {
		if (!isOpen || !roomId) return;
		// Only snapshot if we haven't started editing (no pending changes)
		if (pendingLinks.size > 0 || pendingUnlinks.size > 0) return;
		const linked = new Set();
		for (const f of userFiles) {
			if ((f.linked_room_ids || []).includes(roomId)) {
				linked.add(f.id);
			}
		}
		initialLinkedRef.current = linked;
	}, [isOpen, userFiles, roomId]); // eslint-disable-line react-hooks/exhaustive-deps

	// Poll for processing files
	useEffect(() => {
		if (!isOpen) return;
		const hasProcessing = userFiles.some(f => f.processing_status === 'processing');
		if (!hasProcessing) return;
		const timer = setInterval(() => fetchUserFiles(), 4000);
		return () => clearInterval(timer);
	}, [isOpen, userFiles]); // eslint-disable-line react-hooks/exhaustive-deps

	// Effective linked state: initial + pendingLinks - pendingUnlinks
	const isEffectivelyLinked = useCallback((fileId) => {
		if (pendingLinks.has(fileId)) return true;
		if (pendingUnlinks.has(fileId)) return false;
		return initialLinkedRef.current.has(fileId);
	}, [pendingLinks, pendingUnlinks]);

	const handleToggleLink = (file) => {
		if (!roomId || isLegacyRoom || file.processing_status === 'error') return;
		const fileId = file.id;
		const wasLinked = initialLinkedRef.current.has(fileId);
		const currentlyLinked = isEffectivelyLinked(fileId);

		if (currentlyLinked) {
			// User wants to unlink
			if (wasLinked) {
				// Was originally linked — add to pendingUnlinks
				setPendingUnlinks(prev => new Set(prev).add(fileId));
				setPendingLinks(prev => { const n = new Set(prev); n.delete(fileId); return n; });
			} else {
				// Was added in this session — just remove from pendingLinks
				setPendingLinks(prev => { const n = new Set(prev); n.delete(fileId); return n; });
			}
		} else {
			// User wants to link
			if (wasLinked) {
				// Was originally linked but user unlinked — cancel the unlink
				setPendingUnlinks(prev => { const n = new Set(prev); n.delete(fileId); return n; });
			} else {
				// New link
				setPendingLinks(prev => new Set(prev).add(fileId));
			}
		}
	};

	// Determine if there are pending changes
	const hasPendingFileChanges = pendingLinks.size > 0 || pendingUnlinks.size > 0;
	const hasPendingUploads = pendingFiles.length > 0;
	const hasAnyPendingChanges = hasPendingFileChanges || hasPendingUploads;

	const handleDropZoneDrop = useCallback((e) => {
		e.preventDefault();
		e.stopPropagation();
		if (e.dataTransfer?.files?.length > 0) {
			const files = Array.from(e.dataTransfer.files);
			const valid = files.filter(file => {
				const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
				return allowedExtensions.includes(ext) && file.size <= maxSize;
			});
			if (valid.length > 0) {
				setPendingFiles(prev => [...prev, ...valid]);
			}
		}
	}, [setPendingFiles, allowedExtensions]);

	const handleSubmit = useCallback(async () => {
		if (isApplying || isUploading) return;
		setIsApplying(true);

		try {
			let uploadedFileIds = [];
			let urlFileIds = [];

			const { urls, connector, sequenceMeta } = uploadPanelRef.current?.getSubmitData() || {};

			// 1. Upload pending files
			if (pendingFiles.length > 0) {
				uploadedFileIds = await onUploadFiles(pendingFiles, connector, sequenceMeta);
				setPendingFiles([]);
			}

			// 2. Upload URL sources
			if (urls?.length > 0) {
				for (const { url, label } of urls) {
					const ids = await onLoadUrl(url, label.trim());
					if (ids?.length > 0) urlFileIds.push(...ids);
				}
			}

			// 3. Batch apply all changes (link/unlink) in one call
			// Collection metadata (time_mode, time_delta) is stored on the
			// UserFile records at upload time — the backend reads it from DB.
			const allLinkIds = [...pendingLinks, ...uploadedFileIds, ...urlFileIds];
			const allUnlinkIds = [...pendingUnlinks];

			if (allLinkIds.length > 0 || allUnlinkIds.length > 0) {
				await onApplyChanges(allLinkIds, allUnlinkIds);
			}

			uploadPanelRef.current?.reset();
			setPendingLinks(new Set());
			setPendingUnlinks(new Set());
			onClose();
		} catch (err) {
			console.error('Apply failed:', err);
		} finally {
			setIsApplying(false);
		}
	}, [isApplying, isUploading, pendingFiles, pendingLinks, pendingUnlinks,
		onUploadFiles, onLoadUrl, onApplyChanges, onClose, setPendingFiles]);

	const handleKeyDown = useCallback((e) => {
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
		}
	}, [onClose]);

	if (!isOpen) return null;

	const canSubmit = hasAnyPendingChanges;
	const submitLabel = isApplying || isUploading
		? (isUploading ? filesStatus : t("chat.applying"))
		: hasPendingFileChanges || hasPendingUploads
			? t("chat.apply")
			: t("chat.load");

	return (
		<div
			className={styles.overlay}
			onClick={onClose}
			onKeyDown={handleKeyDown}
			onDragOver={e => e.preventDefault()}
			onDrop={handleDropZoneDrop}
		>
			<div className={styles.modalGlassBg} onClick={e => e.stopPropagation()}>
				<div className={styles.modal}>
					<div className={styles.header}>
						<div className={styles.title}>{t("chat.dataSources")}</div>
						<button className={styles.closeButton} onClick={onClose} data-tooltip={t("cancel")}>
							<IoClose />
						</button>
					</div>

					<div className={styles.body}>
						{isLegacyRoom && (
							<div style={{
								padding: '8px 14px',
								marginBottom: '10px',
								borderRadius: '6px',
								backgroundColor: 'rgba(255, 152, 0, 0.15)',
								border: '1px solid rgba(255, 152, 0, 0.3)',
								color: '#ffb74d',
								fontSize: '0.8rem',
							}}>
								{t("data.legacyRoomBanner")}
							</div>
						)}
						{uploadError && (
							<div className={styles.uploadErrorBanner}>
								<span>{uploadError}</span>
								<button className={styles.uploadErrorClose} onClick={clearUploadError}>&times;</button>
							</div>
						)}
						{/* Your Files (link/unlink to room) */}
						<div className={styles.section}>
							<div className={styles.sectionHeader}>{t("chat.yourFilesTitle")} <span className={styles.sectionHint}>– {t("chat.yourFilesHint")}</span></div>
							{userFiles.length === 0 ? (
								<div className={styles.noSources}>{t("chat.noActiveSources")}</div>
							) : (
								<div className={styles.fileLibrary}>
									{userFiles.map((file) => {
										const effectiveLinked = isEffectivelyLinked(file.id);
										const wasLinked = initialLinkedRef.current.has(file.id);
										const changed = effectiveLinked !== wasLinked;
										const isProcessing = file.processing_status === 'processing';
										const isError = file.processing_status === 'error';
										return (
											<label
												key={file.id}
												className={`${styles.fileLibraryItem} ${effectiveLinked ? styles.fileLibraryItemLinked : ''} ${changed ? styles.fileLibraryItemChanged : ''}`}
												data-tooltip={isLegacyRoom ? t("data.legacyRoomDisabled") : isProcessing ? t("data.processingTooltip") : isError ? t("data.processingErrorTooltip") : undefined}
											>
												<input
													type="checkbox"
													className={styles.fileCheckbox}
													checked={effectiveLinked}
													disabled={isLegacyRoom || isProcessing || isError || isApplying}
													onChange={() => handleToggleLink(file)}
												/>
												<span className={styles.fileLibraryIcon}>
													{getFileIcon(file)}
												</span>
												<span className={styles.fileLibraryName}>
													{file.display_name || file.original_name}
												</span>
												<span className={styles.fileLibrarySize}>
													{formatBytes(file.size_bytes)}
												</span>
												{isProcessing && (
													<span className={styles.processingBadge}>
														<AiOutlineLoading3Quarters className={styles.processingSpinner} />
														{t("data.processing")}
													</span>
												)}
												{isError && (
													<span className={styles.errorBadge}>
														{t("data.processingError")}
													</span>
												)}
												{effectiveLinked && !isProcessing && !isError && !changed && (
													<span className={styles.linkedBadge}>
														{t("data.linkedToRoom")}
													</span>
												)}
											</label>
										);
									})}
								</div>
							)}

						</div>

						{/* File Upload & URL Source — side by side */}
						<UploadPanel
							ref={uploadPanelRef}
							pendingFiles={pendingFiles}
							setPendingFiles={setPendingFiles}
							allowedExtensions={allowedExtensions}
							maxFileSize={maxSize}
							t={t}
							secureRequest={secureRequest}
							isSubmitting={isUploading || isApplying}
							fileInputRef={fileInputRef}
						/>
					</div>

					<div className={styles.footer}>
						{(isApplying || isUploading) && (
							<div className={styles.processingStatus}>
								<AiOutlineLoading3Quarters className={styles.processingSpinner} />
								<span>{t("chat.filesProcessing")}</span>
							</div>
						)}
						<button className={styles.cancelButton} onClick={onClose}>
							{t("cancel")}
						</button>
						<button
							className={styles.submitButton}
							onClick={handleSubmit}
							disabled={!canSubmit || isUploading || isApplying}
						>
							{submitLabel}
						</button>
					</div>
				</div>
			</div>
		</div>
	);
}

// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import styles from './VariablePickerModal.module.css';
import {
	TbAbc, TbHash, TbDecimal, TbCalendar, TbToggleLeft, TbBraces,
	TbTag, TbList, TbFingerprint, TbCircleCheck,
	TbArrowBadgeDown, TbArrowBadgeUp, TbEye,
} from 'react-icons/tb';

const displayName = (name) => name.replace(/_/g, ' ');

const TYPE_ICON_MAP = {
	STRING:   TbAbc,
	INTEGER:  TbHash,
	FLOAT:    TbDecimal,
	DATETIME: TbCalendar,
	BOOLEAN:  TbToggleLeft,
	OBJECT:   TbBraces,
};

const TYPE_COLOR_MAP = {
	STRING:   { bg: 'rgba(247, 221, 88, 0.12)', border: 'rgba(247, 221, 88, 0.25)', color: '#F7DD58' },
	INTEGER:  { bg: 'rgba(237, 115, 88, 0.12)', border: 'rgba(237, 115, 88, 0.25)', color: '#ED7358' },
	FLOAT:    { bg: 'rgba(230, 30, 128, 0.12)', border: 'rgba(230, 30, 128, 0.25)', color: '#E61E80' },
	DATETIME: { bg: 'rgba(117, 73, 146, 0.12)', border: 'rgba(117, 73, 146, 0.25)', color: '#754992' },
	BOOLEAN:  { bg: 'rgba(13, 79, 176, 0.12)', border: 'rgba(13, 79, 176, 0.25)', color: '#0D4FB0' },
	OBJECT:   { bg: 'rgba(23, 131, 196, 0.12)', border: 'rgba(23, 131, 196, 0.25)', color: '#1783C4' },
};

function TypeIcon({ type, size = 14, className = '' }) {
	const Icon = TYPE_ICON_MAP[type];
	const colors = TYPE_COLOR_MAP[type] || TYPE_COLOR_MAP.OBJECT;
	if (!Icon) return null;
	return <Icon size={size} color={colors.color} className={className} />;
}

/**
 * Format a field min/max value for display.
 *
 * DATETIME fields carry nanoseconds-since-epoch (int64). We convert to
 * milliseconds for JavaScript's ``Date`` and render a human-readable
 * ISO-ish string. Other types pass through ``String(val)``.
 */
function formatFieldValue(val, dataType) {
	if (val == null) return '';
	if (dataType === 'DATETIME') {
		const ns = typeof val === 'string' ? Number(val) : val;
		if (!Number.isFinite(ns)) return String(val);
		const date = new Date(ns / 1_000_000);
		if (isNaN(date.getTime())) return String(val);
		// Pad to YYYY-MM-DD HH:MM:SS (local time)
		const pad = (n) => String(n).padStart(2, '0');
		return (
			`${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
			`${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
		);
	}
	return String(val);
}

/**
 * Parse the "uniques" string from catalogue_stats into { values, truncated }.
 * Format: "['val1', 'val2' ... 'valN']"  (the ... indicates truncated middle)
 */
function parseUniques(raw) {
	if (!raw || typeof raw !== 'string') return { values: [], truncated: false };
	const trimmed = raw.trim();
	if (!trimmed || trimmed === '[]') return { values: [], truncated: false };

	// Check for truncation marker
	const truncated = trimmed.includes(' ... ');

	// Split on the ... marker if present, parse each half
	const halves = trimmed.replace(/^\[|\]$/g, '').split(/\s\.\.\.\s/);
	const values = [];
	for (const half of halves) {
		// Match quoted strings (single or double) allowing escaped quotes inside
		const matches = half.match(/'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"/g);
		if (matches) {
			for (const m of matches) {
				values.push(m.slice(1, -1).replace(/\\'/g, "'").replace(/\\"/g, '"'));
			}
		}
	}
	return { values, truncated };
}

function FieldDetailPanel({ field, dataset, t }) {
	if (!field) {
		return (
			<div className={styles.detailEmpty}>
				{t('chat.variablePickerHint')}
			</div>
		);
	}

	const hasMetadata = !!field.data_type;
	if (!hasMetadata) {
		return (
			<div className={styles.detailEmpty}>
				{displayName(field.name)}
			</div>
		);
	}

	const { values: samples, truncated } = parseUniques(field.uniques);
	const colors = TYPE_COLOR_MAP[field.data_type] || TYPE_COLOR_MAP.OBJECT;

	return (
		<div className={styles.detailContent}>
			<div className={styles.detailFieldName}>
				<TypeIcon type={field.data_type} size={20} />
				{displayName(field.name)}
			</div>

			<div className={styles.detailGrid}>
				<div className={styles.detailLabel}><TbTag size={20} /> {t('chat.variablePickerType')}</div>
				<div className={styles.detailValue}>
					<span
						className={styles.typeBadge}
						style={{ background: colors.bg, borderColor: colors.border, color: colors.color }}
					>
						<TypeIcon type={field.data_type} size={20} />
						{field.data_type}
					</span>
				</div>

				{dataset?.row_count != null && (
					<>
						<div className={styles.detailLabel}><TbList size={20} /> {t('chat.variablePickerRows')}</div>
						<div className={styles.detailValue}>{Number(dataset.row_count).toLocaleString()}</div>
					</>
				)}

				{field.distinct_count != null && (
					<>
						<div className={styles.detailLabel}><TbFingerprint size={20} /> {t('chat.variablePickerDistinct')}</div>
						<div className={styles.detailValue}>{Number(field.distinct_count).toLocaleString()}</div>
					</>
				)}

				{field.is_unique != null && (
					<>
						<div className={styles.detailLabel}><TbCircleCheck size={15} /> {t('chat.variablePickerUnique')}</div>
						<div className={styles.detailValue}>
							{field.is_unique ? t('chat.variablePickerYes') : t('chat.variablePickerNo')}
						</div>
					</>
				)}

				{field.min_value != null && (
					<>
						<div className={styles.detailLabel}><TbArrowBadgeDown size={15} /> {t('chat.variablePickerMin')}</div>
						<div className={styles.detailValue}>{formatFieldValue(field.min_value, field.data_type)}</div>
					</>
				)}

				{field.max_value != null && (
					<>
						<div className={styles.detailLabel}><TbArrowBadgeUp size={15} /> {t('chat.variablePickerMax')}</div>
						<div className={styles.detailValue}>{formatFieldValue(field.max_value, field.data_type)}</div>
					</>
				)}
			</div>

			{samples.length > 0 && (
				<div className={styles.detailSamples}>
					<div className={styles.detailSamplesLabel}><TbEye size={15} /> {t('chat.variablePickerSample')}</div>
					<div className={styles.detailSamplesList}>
						{samples.map((v, i) => (
							<span key={i} className={styles.sampleChip}>{v}</span>
						))}
						{truncated && <span className={styles.sampleMore}>...</span>}
					</div>
				</div>
			)}
		</div>
	);
}

export default function VariablePickerModal({ isOpen, onClose, onSelect, datasets, initialFilter = '', t }) {
	const [search, setSearch] = useState('');
	const [focusedIndex, setFocusedIndex] = useState(0);
	const searchRef = useRef(null);
	const pillRefs = useRef([]);
	const isKeyboardNav = useRef(false);

	useEffect(() => {
		if (isOpen) {
			setSearch(initialFilter);
			setFocusedIndex(0);
			// Don't reset pillRefs here — this effect runs AFTER React's ref
			// callbacks have already populated the array during commit.
			// Resetting here would wipe the freshly-set refs.
			isKeyboardNav.current = false;
			requestAnimationFrame(() => searchRef.current?.focus());
		}
	}, [isOpen, initialFilter]);

	const query = search.toLowerCase().trim();

	const { filteredDatasets, flatItems } = useMemo(() => {
		const filtered = [];
		const flat = [];
		for (const ds of datasets) {
			const matchingFields = ds.fields.filter(f =>
				f.name.toLowerCase().includes(query) ||
				ds.name.toLowerCase().includes(query) ||
				f.name.replace(/_/g, ' ').toLowerCase().includes(query)
			);
			if (matchingFields.length > 0) {
				filtered.push({ ...ds, fields: matchingFields });
				for (const field of matchingFields) {
					flat.push({ datasetName: ds.name, fieldName: field.name, field, dataset: ds });
				}
			}
		}
		return { filteredDatasets: filtered, flatItems: flat };
	}, [datasets, query]);

	const cardBoundaries = useMemo(() => {
		const boundaries = [];
		let offset = 0;
		for (const ds of filteredDatasets) {
			boundaries.push({ start: offset, count: ds.fields.length });
			offset += ds.fields.length;
		}
		return boundaries;
	}, [filteredDatasets]);

	const getCardForIndex = useCallback((idx) => {
		for (let c = 0; c < cardBoundaries.length; c++) {
			const { start, count } = cardBoundaries[c];
			if (idx >= start && idx < start + count) {
				return { cardIndex: c, posInCard: idx - start };
			}
		}
		return { cardIndex: 0, posInCard: 0 };
	}, [cardBoundaries]);

	useEffect(() => {
		setFocusedIndex(i => Math.min(i, Math.max(0, flatItems.length - 1)));
	}, [flatItems.length]);

	useEffect(() => {
		const el = pillRefs.current[focusedIndex];
		if (el) el.scrollIntoView({ block: 'nearest' });
	}, [focusedIndex]);

	const handleSelect = useCallback((item) => {
		if (item) {
			onSelect(item);
			onClose();
		}
	}, [onSelect, onClose]);

	// Only consider pills that are visible within their scroll container.
	// Pills scrolled out of a card's .pillGrid would have rects outside the
	// container bounds — navigating to them would skip over cards below.
	const isVisibleInContainer = useCallback((el) => {
		const scrollParent = el.parentElement;
		if (!scrollParent) return true;
		const sr = scrollParent.getBoundingClientRect();
		const er = el.getBoundingClientRect();
		return er.bottom > sr.top + 2 && er.top < sr.bottom - 2;
	}, []);

	// Two-phase spatial navigation:
	//   1. Find the nearest row (up/down) or column (left/right) among visible pills
	//   2. Within that row/column, pick the closest pill on the other axis
	const navigateSpatial = useCallback((direction) => {
		const currentEl = pillRefs.current[focusedIndex];
		if (!currentEl) return false;
		const cur = currentEl.getBoundingClientRect();
		const curCX = cur.left + cur.width / 2;
		const curCY = cur.top + cur.height / 2;

		const candidates = [];
		pillRefs.current.forEach((el, idx) => {
			if (!el || idx === focusedIndex) return;
			if (!isVisibleInContainer(el)) return;
			const r = el.getBoundingClientRect();
			let valid = false;
			switch (direction) {
				case 'right': valid = r.left > cur.right - 4; break;
				case 'left':  valid = r.right < cur.left + 4; break;
				case 'down':  valid = r.top > cur.bottom - 4; break;
				case 'up':    valid = r.bottom < cur.top + 4; break;
			}
			if (valid) {
				candidates.push({
					idx,
					rect: r,
					cx: r.left + r.width / 2,
					cy: r.top + r.height / 2,
				});
			}
		});

		if (candidates.length === 0) return false;

		let bestIdx;

		if (direction === 'up' || direction === 'down') {
			const nearestEdge = direction === 'up'
				? Math.max(...candidates.map(c => c.rect.bottom))
				: Math.min(...candidates.map(c => c.rect.top));
			const rowCandidates = candidates.filter(c => {
				const edge = direction === 'up' ? c.rect.bottom : c.rect.top;
				return Math.abs(edge - nearestEdge) < 8;
			});
			let bestDist = Infinity;
			for (const c of rowCandidates) {
				const dist = Math.abs(c.cx - curCX);
				if (dist < bestDist) { bestDist = dist; bestIdx = c.idx; }
			}
		} else {
			const nearestEdge = direction === 'right'
				? Math.min(...candidates.map(c => c.rect.left))
				: Math.max(...candidates.map(c => c.rect.right));
			const colCandidates = candidates.filter(c => {
				const edge = direction === 'right' ? c.rect.left : c.rect.right;
				return Math.abs(edge - nearestEdge) < 8;
			});
			let bestDist = Infinity;
			for (const c of colCandidates) {
				const dist = Math.abs(c.cy - curCY);
				if (dist < bestDist) { bestDist = dist; bestIdx = c.idx; }
			}
		}

		if (bestIdx != null) {
			setFocusedIndex(bestIdx);
			return true;
		}
		return false;
	}, [focusedIndex, isVisibleInContainer]);

	const handleModalKeyDown = useCallback((e) => {
		if (e.key === 'Escape') {
			e.preventDefault();
			onClose();
			return;
		}

		const isInSearch = document.activeElement === searchRef.current;

		if (e.key === 'Enter' && flatItems.length > 0 && !isInSearch) {
			e.preventDefault();
			handleSelect(flatItems[focusedIndex]);
			return;
		}

		if (e.key === 'Tab') {
			e.preventDefault();
			if (isInSearch) {
				pillRefs.current[focusedIndex]?.focus();
			} else {
				searchRef.current?.focus();
			}
			return;
		}

		// When search input is focused, let arrows work normally for cursor movement.
		// ArrowDown to exit search is handled in the search input's own onKeyDown.
		if (isInSearch) return;

		// Arrow keys: spatial navigation across visible pills
		if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
			if (flatItems.length === 0) return;
			e.preventDefault();
			isKeyboardNav.current = true;

			const dirMap = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down' };
			const moved = navigateSpatial(dirMap[e.key]);

			if (!moved && e.key === 'ArrowUp') {
				searchRef.current?.focus();
			}
			return;
		}

		// Any printable character typed while on a pill: redirect to search
		if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
			searchRef.current?.focus();
			return;
		}
	}, [flatItems, focusedIndex, handleSelect, onClose, navigateSpatial]);

	useEffect(() => {
		if (document.activeElement !== searchRef.current) {
			pillRefs.current[focusedIndex]?.focus();
		}
	}, [focusedIndex]);

	if (!isOpen) return null;

	const activeCardIndex = flatItems.length > 0 ? getCardForIndex(focusedIndex).cardIndex : -1;
	const focusedItem = flatItems[focusedIndex] || null;
	const hasDetails = focusedItem?.field?.data_type;

	let pillIndex = 0;

	return (
		<div className={styles.overlay} onClick={onClose} onKeyDown={handleModalKeyDown}>
			<div className={`${styles.modalGlassBg} ${hasDetails ? styles.modalGlassBgWide : ''}`} onClick={e => e.stopPropagation()}>
				<div className={`${styles.modal} ${hasDetails ? styles.modalWide : ''}`}>
					<div className={styles.header}>
						<div className={styles.title}>{t('chat.variablePickerTitle')}</div>
						<input
							ref={searchRef}
							type="text"
							className={styles.searchInput}
							placeholder={t('chat.variablePickerSearch')}
							value={search}
							onChange={e => setSearch(e.target.value)}
							onKeyDown={e => {
								if (e.key === 'ArrowDown' && flatItems.length > 0) {
									e.preventDefault();
									e.stopPropagation();
									isKeyboardNav.current = true;
									setFocusedIndex(0);
									// Directly focus the first pill (setFocusedIndex may not
									// trigger the effect if index was already 0)
									requestAnimationFrame(() => pillRefs.current[0]?.focus());
								}
								if (e.key === 'Enter' && flatItems.length > 0) {
									e.preventDefault();
									e.stopPropagation();
									handleSelect(flatItems[focusedIndex]);
								}
							}}
						/>
					</div>
					<div className={styles.mainContent}>
						<div
							className={styles.body}
							onMouseMove={() => { isKeyboardNav.current = false; }}
						>
							{filteredDatasets.length === 0 ? (
								<div className={styles.emptyMessage}>{t('chat.variablePickerEmpty')}</div>
							) : (
								<div className={styles.cardsGrid}>
									{filteredDatasets.map((ds, dsIdx) => {
										const isActiveCard = dsIdx === activeCardIndex;
										return (
											<div
												key={ds.data_id}
												className={`${styles.datasetCard} ${isActiveCard ? styles.cardActive : ''}`}
											>
												<div className={styles.datasetHeader}>{displayName(ds.name)}</div>
												<div className={styles.pillGrid}>
													{ds.fields.map((field) => {
														const idx = pillIndex++;
														const isFocused = idx === focusedIndex;
														return (
															<button
																key={`${ds.data_id}-${field.name}`}
																ref={el => { pillRefs.current[idx] = el; }}
																className={`${styles.pill} ${isFocused ? styles.focused : ''}`}
																tabIndex={-1}
																onClick={() => handleSelect({ datasetName: ds.name, fieldName: field.name })}
																onMouseEnter={() => {
																	if (!isKeyboardNav.current) setFocusedIndex(idx);
																}}
															>
																{field.data_type && (
																	<TypeIcon type={field.data_type} size={19} className={styles.pillTypeIcon} />
																)}
																{displayName(field.name)}
															</button>
														);
													})}
												</div>
											</div>
										);
									})}
								</div>
							)}
						</div>
						{hasDetails && (
							<div className={styles.detailPanel}>
								<FieldDetailPanel
									field={focusedItem?.field}
									dataset={focusedItem ? datasets.find(d => d.name === focusedItem.datasetName) : null}
									t={t}
								/>
							</div>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}

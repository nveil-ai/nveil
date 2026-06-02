// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from './SequenceOptions.module.css';

/**
 * Temporal sequence options — shown when the user checks "Treat as temporal sequence".
 *
 * Provides mode toggle (index / time-based / auto) and time delta input.
 * Fully generic — no format-specific logic.
 */
export default function SequenceOptions({
	isSequence, setIsSequence,
	timeMode, setTimeMode,
	deltaValue, setDeltaValue,
	deltaUnit, setDeltaUnit,
	t = (k, d) => d || k,
}) {
	return (
		<div className={styles.section}>
			<label className={styles.checkbox}>
				<input type="checkbox" checked={isSequence}
					onChange={(e) => setIsSequence(e.target.checked)} />
				<span>{t("data.sequenceLabel", "Treat as temporal sequence")}</span>
			</label>
			{isSequence && (
				<div className={styles.options}>
					<label className={`${styles.card} ${timeMode === 'index' ? styles.cardActive : ''}`}>
						<input type="radio" name="seqMode" value="index"
							checked={timeMode === 'index'}
							onChange={() => setTimeMode('index')} />
						<div className={styles.cardContent}>
							<span className={styles.cardTitle}>{t("data.sequenceIndex", "Index-based")}</span>
							<span className={styles.cardDesc}>{t("data.sequenceIndexDesc", "Files play in order, one after another. No time semantics.")}</span>
						</div>
					</label>
					<label className={`${styles.card} ${timeMode === 'time_based' ? styles.cardActive : ''}`}>
						<input type="radio" name="seqMode" value="time_based"
							checked={timeMode === 'time_based'}
							onChange={() => setTimeMode('time_based')} />
						<div className={styles.cardContent}>
							<span className={styles.cardTitle}>{t("data.sequenceTimeBased", "Time-based")}</span>
							<span className={styles.cardDesc}>{t("data.sequenceTimeBasedDesc", "Specify the real time interval between each file.")}</span>
						</div>
					</label>
					<label className={`${styles.card} ${timeMode === 'auto' ? styles.cardActive : ''}`}>
						<input type="radio" name="seqMode" value="auto"
							checked={timeMode === 'auto'}
							onChange={() => setTimeMode('auto')} />
						<div className={styles.cardContent}>
							<span className={styles.cardTitle}>{t("data.sequenceAuto", "Auto-detect")}</span>
							<span className={styles.cardDesc}>{t("data.sequenceAutoDesc", "Infer timing from file metadata (e.g. simulation output).")}</span>
						</div>
					</label>
					{timeMode === 'time_based' && (
						<div className={styles.delta}>
							<span className={styles.deltaLabel}>{t("data.sequenceDeltaLabel", "Interval between frames:")}</span>
							<input type="number" min={1} value={deltaValue}
								onChange={(e) => setDeltaValue(Math.max(1, Number(e.target.value) || 1))}
								className={styles.deltaInput} />
							<select value={deltaUnit}
								onChange={(e) => setDeltaUnit(e.target.value)}
								className={styles.deltaSelect}>
								<option value="s">{t("data.seconds", "seconds")}</option>
								<option value="m">{t("data.minutes", "minutes")}</option>
								<option value="h">{t("data.hours", "hours")}</option>
								<option value="d">{t("data.days", "days")}</option>
							</select>
						</div>
					)}
				</div>
			)}
		</div>
	);
}

/**
 * Build ISO 8601 duration string from sequence options.
 * Returns null if not in time_based mode.
 */
export function buildIsoDuration(timeMode, deltaValue, deltaUnit) {
	if (timeMode !== 'time_based') return null;
	const UNIT_MAP = { s: 'S', m: 'M', h: 'H', d: 'D' };
	const isoUnit = UNIT_MAP[deltaUnit] || 'S';
	return deltaUnit === 'd'
		? `P${deltaValue}D`
		: `PT${deltaValue}${isoUnit}`;
}

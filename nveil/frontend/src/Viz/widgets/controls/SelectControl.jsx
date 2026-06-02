// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState, useMemo } from 'react';
import { getIcon } from '../iconMap';
import { MdExpandMore } from 'react-icons/md';
import styles from './SelectControl.module.css';

/**
 * Inline dropdown — renders ListBox directly when open (no overlay teleport).
 * This avoids the sidebar-collapse-on-dropdown problem entirely.
 */
export default function SelectControl({ label, icon, items = [], value, onChange }) {
    const [open, setOpen] = useState(false);
    const sortedItems = useMemo(() =>
        [...items].sort((a, b) => a.title.localeCompare(b.title, undefined, { numeric: true, sensitivity: 'base' })),
        [items]
    );
    const selectedItem = sortedItems.find(i => i.value === value);

    return (
        <div className={styles.wrapper}>
            <div className={styles.header}>
                {icon && <span className={styles.icon}>{getIcon(icon)}</span>}
                <span className={styles.label}>{label}</span>
            </div>
            <button
                className={`${styles.trigger} ${open ? styles.triggerOpen : ''}`}
                onClick={() => setOpen(!open)}
                type="button"
            >
                <span className={styles.triggerText}>{selectedItem?.title || value || '—'}</span>
                <MdExpandMore className={`${styles.chevron} ${open ? styles.chevronOpen : ''}`} />
            </button>
            {open && (
                <div className={styles.listbox} role="listbox">
                    {sortedItems.map((item) => (
                        <button
                            key={item.value}
                            role="option"
                            aria-selected={item.value === value}
                            className={`${styles.option} ${item.value === value ? styles.optionSelected : ''}`}
                            onClick={() => { onChange(item.value); setOpen(false); }}
                            type="button"
                        >
                            {item.title}
                        </button>
                    ))}
                </div>
            )}
        </div>
    );
}

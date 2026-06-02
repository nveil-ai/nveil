// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from 'react';
import { MdExpandMore } from 'react-icons/md';
import { getIcon } from '../iconMap';
import styles from './WidgetGroup.module.css';

/**
 * Simple collapsible group — no React Aria Disclosure (which requires
 * specific slot patterns). Just a button that toggles a div.
 */
export default function WidgetGroup({ label, icon, expanded = false, children }) {
    const [isOpen, setIsOpen] = useState(expanded);

    return (
        <div className={styles.group}>
            <button className={styles.header} onClick={() => setIsOpen(!isOpen)} type="button">
                {icon && <span className={styles.icon}>{getIcon(icon)}</span>}
                <span className={styles.label}>{label}</span>
                <MdExpandMore className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} />
            </button>
            {isOpen && (
                <div className={styles.content}>
                    {children}
                </div>
            )}
        </div>
    );
}

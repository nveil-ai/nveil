// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from 'react';
import { MdInfoOutline, MdExpandMore } from 'react-icons/md';
import styles from './InfoPanel.module.css';

export default function InfoPanel({ title, text }) {
    const [isOpen, setIsOpen] = useState(false);

    return (
        <div className={styles.info}>
            <button className={styles.header} onClick={() => setIsOpen(!isOpen)} type="button">
                <MdInfoOutline className={styles.icon} />
                <span className={styles.title}>{title}</span>
                <MdExpandMore className={`${styles.chevron} ${isOpen ? styles.chevronOpen : ''}`} />
            </button>
            {isOpen && <p className={styles.text}>{text}</p>}
        </div>
    );
}

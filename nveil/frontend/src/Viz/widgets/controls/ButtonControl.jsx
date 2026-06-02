// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

import { getIcon } from '../iconMap';
import styles from './ButtonControl.module.css';

export default function ButtonControl({ label, icon, variant, disabled, onClick }) {
    const variantClass = variant === 'primary' ? styles.btnPrimary
        : variant === 'warning' ? styles.btnWarning
        : '';

    return (
        <div className={styles.wrapper}>
            <button
                className={`${styles.btn} ${variantClass}`}
                disabled={disabled}
                onClick={onClick}
            >
                {icon && <span className={styles.icon}>{getIcon(icon)}</span>}
                <span>{label}</span>
            </button>
        </div>
    );
}

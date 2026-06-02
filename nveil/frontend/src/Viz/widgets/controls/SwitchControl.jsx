// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { Switch } from 'react-aria-components';
import { getIcon } from '../iconMap';
import styles from './SwitchControl.module.css';

export default function SwitchControl({ label, icon, value, onChange }) {
    return (
        <Switch
            className={styles.switch}
            isSelected={value}
            onChange={onChange}
        >
            <div className={styles.track}>
                <div className={styles.knob} />
            </div>
            <div className={styles.labelWrap}>
                {icon && <span className={styles.icon}>{getIcon(icon)}</span>}
                <span className={styles.label}>{label}</span>
            </div>
        </Switch>
    );
}

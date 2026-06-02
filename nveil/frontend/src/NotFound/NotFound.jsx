// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Guillaume Franque
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
import { useTranslation } from 'react-i18next';
import styles from './NotFound.module.css';

const NotFound = () => {
    const { t } = useTranslation();
    return (
        <div className={styles.container}>
            <h1 className={styles.title}>404</h1>
            <p className={styles.subtitle}>{t("notFound.title")}</p>
            <a href="/" className={styles.button}>
                {t("notFound.backToHome") || "Back to Home"}
            </a>
        </div>
    );
};


export default NotFound;

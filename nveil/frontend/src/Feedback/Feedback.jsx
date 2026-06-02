// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import styles from "./Feedback.module.css";
import { useTranslation } from "react-i18next";
import { useState, useMemo, useEffect } from "react";
import { useAuth } from "../Auth/AuthContext"
import SEO from "../Components/SEO";



export default function Feedback() {
    const { t } = useTranslation();
     const { user } = useAuth();
    const [iframeSrc, setIframeSrc] = useState(null);
useEffect(() => {
    setIframeSrc('/feedback/app/');

}, [user]);

    return (
        <>
        <SEO
            title={t('seo.feedbackTitle')}
            description={t('seo.feedbackDescription')}
            url="https://app.nveil.com/feedback"
        />
        <div className={styles.feedbackContainer}>
            <div className={styles.content} style={{ width: "100%", overflow: "hidden" }}>
                <div className={styles.feedbackPanel}>
                <iframe 
                    id="feedback-iframe"
                    allowTransparency="true"
                    src="https://feedback.nveil.com"
                    className={styles.feedbackIframe}
                />


                    {/* <div className={styles.feedbackGroup}>
                        <div className={styles.groupTitle}>{t("feedback.vizTypes")}</div>

                    </div>
                    <div className={styles.feedbackGroup}>
                        <div className={styles.groupTitle}>{t("feedback.colorPalettes")}</div>
                    </div> */}
                </div>
            </div>
        </div>
        </>
    );
}

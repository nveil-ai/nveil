// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, { useState, useImperativeHandle, forwardRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../Auth/AuthContext';

const WelcomeMessage = React.memo(
	forwardRef(function WelcomeMessage({ styles, isAuthenticated }, ref) {
		const { setShowAuthModal: setShowAuth } = useAuth();
		const { t, i18n } = useTranslation();
		const [visible, setVisible] = useState(false);

		useImperativeHandle(ref, () => ({
			hide: () => setVisible(false),
			show: () => setVisible(true),
		}));

		if (!visible) return null;

		return (
			<div className={styles.welcomeHolder}>
				<div className={styles.welcomeMessage}>
					{i18n.randomT("chat.welcomeTitle")}
					<div className={styles.welcomeSubTitle}>{i18n.randomT("chat.welcomeMessages")}</div>
					{!isAuthenticated && (
						<button
							className={styles.loginButton}
							onClick={() => setShowAuth(true)}
						>
							{t("chat.login")}
						</button>
					)}
				</div>
			</div>
		);
	})
);

export default WelcomeMessage;

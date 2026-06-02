// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

// src/components/CookieBanner.jsx
import React, { useState, useEffect } from "react";
import { useCookies } from "react-cookie";
import { useTranslation } from "react-i18next";
import { updateConsent } from "../utils/analytics";

export default function CookieBanner() {
  const { t } = useTranslation();
  const [cookies, setCookie, removeCookie] = useCookies(["cookieConsent"]);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Show banner only if the visitor has never made a choice
    if (cookies.cookieConsent === undefined) {
      setIsVisible(true);
    }
    // Returning visitors: consent is already restored in index.html
    // before GTM even loads — no need to call updateConsent here.
  }, [cookies.cookieConsent]);

  const handleChoice = (choice) => {
    const isGranted = choice === "accept";

    // 1. Persist choice (365 days)
    setCookie("cookieConsent", isGranted, { path: "/", maxAge: 31536000 });

    // 2. Push consent update to GTM — tags fire (or stay blocked) accordingly
    updateConsent(isGranted);

    // 3. Hide banner
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div role="dialog" aria-live="polite" aria-label={t("cookieBanner.message")} style={styles.banner}>
      <p style={styles.text}>{t("cookieBanner.message")}</p>
      <div style={styles.buttons}>
        <button
          onClick={() => handleChoice("deny")}
          style={styles.denyBtn}
          onMouseEnter={(e) => {
            e.target.style.backgroundColor = '#333';
            e.target.style.color = 'white';
          }}
          onMouseLeave={(e) => {
            e.target.style.backgroundColor = 'transparent';
            e.target.style.color = '#ccc';
          }}
        >
          {t("cookieBanner.deny")}
        </button>
        <button
          onClick={() => handleChoice("accept")}
          style={styles.acceptBtn}
          onMouseEnter={(e) => e.target.style.opacity = '0.9'}
          onMouseLeave={(e) => e.target.style.opacity = '1'}
          aria-label={t("cookieBanner.accept")}
        >
          {t("cookieBanner.accept")}
        </button>
        <a href={t("cookieBanner.learnMoreUrl")} style={{ marginLeft: 12, color: '#ccc', fontSize: '13px', alignSelf: "center" }} target="_blank" rel="noopener noreferrer">
          {t("cookieBanner.learnMore")}
        </a>
      </div>
    </div>
  );
};

// Customized styles to match your app's theme
const styles = {
  banner: {
    position: "fixed",
    bottom: "0px",
    left: "0px",
    right: "0px",
    backgroundColor: "rgb(20 20 20 / 63%)",
    backdropFilter: "blur(10px)",
    borderTop: "1px solid rgb(51, 51, 51)",
    padding: "15px 20px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    zIndex: 9999,
    boxShadow: "rgba(0, 0, 0, 0.2) 0px -2px 10px",
    width: "80%",
    placeSelf: "center",
    borderRadius: "8px",
  },
  text: {
    margin: 0,
    color: "#eee", // Light text color for readability
    fontSize: "14px",
    maxWidth: "1000px"
  },
  buttons: { display: "flex", gap: "10px" },
  acceptBtn: { 
    padding: "8px 20px", 
    // Gradient background similar to your app's theme
    background: "linear-gradient(135deg, rgb(73 130 189), rgb(112 80 187))",
    color: "white", 
    border: "none", 
    borderRadius: "20px", // Rounded corners
    cursor: "pointer",
    fontWeight: "bold",
    fontSize: "14px",
    transition: "opacity 0.2s ease-in-out"
  },
  denyBtn: { 
    padding: "8px 20px", 
    backgroundColor: "transparent", // Transparent initially
    color: "#ccc", // Lighter grey text
    border: "1px solid #555", // Subtle border
    borderRadius: "20px", // Rounded corners
    cursor: "pointer",
    fontSize: "14px",
    transition: "all 0.2s ease-in-out"
  }
};
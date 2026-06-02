// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { IoClose } from "react-icons/io5";
import ColorPaletteGenerator from "./ColorPaletteGenerator";
import styles from "./PaletteModal.module.css";

/**
 * Modal for creating custom color palettes
 */
const ColorPaletteModal = React.memo(function ColorPaletteModal({
    isOpen,
    onClose,
    config,
    onSave
}) {
    const { t } = useTranslation();
    const [savedColors, setSavedColors] = useState([]);
    const [savedBreaks, setSavedBreaks] = useState([]);
    const [paletteName, setPaletteName] = useState(config?.name || "custom_palette");
    const [paletteType, setPaletteType] = useState(config?.type || "SEQUENTIAL");
    const [hasReceivedColors, setHasReceivedColors] = useState(false);

    // Reset state when modal opens with new config
    useEffect(() => {
        if (isOpen && config) {
            setPaletteName(config.name || "custom_palette");
            setPaletteType(config.type || "SEQUENTIAL");
            setHasReceivedColors(false);
        }
    }, [isOpen, config]);

    if (!isOpen) return null;

    const handleColorChange = (colors, breaks, min, max) => {
        setSavedColors(colors || []);
        setSavedBreaks((breaks || []).map(b => ({
            anchor: b.anchor,
            position: b.position,
            color: b.color,
            interpolation: b.interpolation,
            locked: !!b.locked,
            lockedValue: b.lockedValue ?? null,
        })));
        setHasReceivedColors(true);
    };

    const handleSave = async () => {
        if (!hasReceivedColors || savedColors.length === 0) {
            alert(t("chat.colorPalette.noColors"));
            return;
        }

        try {
            // 1. Fetch existing metadata first
            let existingPalettes = [];
            try {
                const getResponse = await fetch("/server/files/get_metadata?metadata_name=custom_color_palettes", {
                    method: "GET",
                    credentials: "include"
                });
                if (getResponse.ok) {
                    const data = await getResponse.json();
                    if (data.custom_color_palettes && Array.isArray(data.custom_color_palettes)) {
                        existingPalettes = data.custom_color_palettes;
                    }
                }
            } catch (err) {
                console.warn("Could not fetch existing palettes, starting fresh", err);
            }

            // 2. Add or update the current palette
            const newPalette = {
                name: paletteName,
                colors: savedColors,
                breaks: savedBreaks,
                type: paletteType
            };

            const paletteIndex = existingPalettes.findIndex(p => p.name === paletteName);
            if (paletteIndex >= 0) {
                // Update existing
                existingPalettes[paletteIndex] = newPalette;
            } else {
                // Add new
                existingPalettes.push(newPalette);
            }

            // 3. Save updated list and set active palette name
            const response = await fetch("/server/files/set_metadata", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify({
                    custom_color_palettes: existingPalettes,
                    active_color_palette: paletteName
                })
            });

            if (response.ok) {
                onSave?.(paletteName, savedColors);
                onClose();
            } else {
                console.error("Failed to save color palette");
                alert("Failed to save color palette. Please try again.");
            }
        } catch (err) {
            console.error("Error saving color palette:", err);
            alert("Error saving color palette: " + err.message);
        }
    };

    return (
        <div className={styles.colorPaletteOverlay} onClick={onClose}>
            <div className={styles.colorPaletteModal} onClick={e => e.stopPropagation()}>
                <div className={styles.colorPaletteHeader}>
                    <h3>{t("chat.colorPalette.title")}</h3>
                    <button className={styles.closeButton} onClick={onClose}>
                        <IoClose size={20} />
                    </button>
                </div>
                <div className={styles.colorPaletteContent}>
                    <div className={styles.paletteNameRow}>
                        <div className={styles.paletteNameInput}>
                            <label>{t("chat.colorPalette.name")}</label>
                            <input
                                type="text"
                                value={paletteName}
                                onChange={e => setPaletteName(e.target.value)}
                                placeholder={t("chat.colorPalette.namePlaceholder")}
                            />
                        </div>
                        <div className={styles.paletteTypeInput}>
                            <label>{t("chat.colorPalette.type")}</label>
                            <select
                                value={paletteType}
                                onChange={e => setPaletteType(e.target.value)}
                            >
                                <option value="SEQUENTIAL">{t("chat.colorPalette.typeSequential")}</option>
                                <option value="DIVERGING">{t("chat.colorPalette.typeDiverging")}</option>
                                <option value="QUALITATIVE">{t("chat.colorPalette.typeQualitative")}</option>
                            </select>
                        </div>
                    </div>
                    <ColorPaletteGenerator
                        defaultMinValue={config?.minValue ?? 0}
                        defaultMaxValue={config?.maxValue ?? 1}
                        defaultBreaks={config?.breaks}
                        defaultColorCount={config?.colorCount ?? 10}
                        onChange={handleColorChange}
                    />
                </div>
                <div className={styles.colorPaletteFooter}>
                    <button className={styles.cancelButton} onClick={onClose}>
                        {t("chat.colorPalette.cancel")}
                    </button>
                    <button className={styles.saveButton} onClick={handleSave}>
                        {t("chat.colorPalette.save")}
                    </button>
                </div>
            </div>
        </div>
    );
});

export default function PaletteModal({ chatRef, onPaletteSaved }) {
    const { t } = useTranslation();
    const [showColorPalette, setShowColorPalette] = useState(false);
    const [colorPaletteConfig, setColorPaletteConfig] = useState(null);

    useEffect(() => {
        const handleOpenColorPalette = (event) => {
            const config = event.detail || {};
            setColorPaletteConfig(config);
            setShowColorPalette(true);
        };

        const handleGlobalClick = (e) => {
            // Check if clicked element or parent has the class
            const target = e.target;
            const button = target.closest ? target.closest('.deep-chat-suggestion-color-palette') : null;

            if (button) {
                // If the button has specific config in dataset, use it
                // e.g. data-config='{"name": "foo"}'
                let config = {};
                try {
                    if (button.dataset.config) {
                        config = JSON.parse(button.dataset.config);
                    }
                } catch (err) {
                    console.warn("Failed to parse config from color palette button", err);
                }

                setColorPaletteConfig(config);
                setShowColorPalette(true);
            }
        };

        window.addEventListener('openColorPalette', handleOpenColorPalette);
        window.addEventListener('click', handleGlobalClick);


        return () => {
            window.removeEventListener('openColorPalette', handleOpenColorPalette);
            window.removeEventListener('click', handleGlobalClick);
        };
    }, []);

    const handleSave = useCallback((name, colors) => {
        if (onPaletteSaved) {
            onPaletteSaved(name);
        }
    }, [onPaletteSaved]);

    return (
        <ColorPaletteModal
            isOpen={showColorPalette}
            onClose={() => setShowColorPalette(false)}
            config={colorPaletteConfig}
            onSave={handleSave}
        />
    );
}

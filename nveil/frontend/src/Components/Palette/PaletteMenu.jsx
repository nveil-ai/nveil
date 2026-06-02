// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React, { useState, useEffect } from 'react';
import { Button, Popover, Dialog, ListBox, ListBoxItem, Label, DialogTrigger, OverlayArrow } from 'react-aria-components';
import { useTranslation } from 'react-i18next';
import { IoColorPaletteOutline, IoAdd, IoTrash, IoPencil, IoCheckmark } from 'react-icons/io5';
import styles from './PaletteMenu.module.css';

/**
 * Menu to manage custom color palettes
 */
export default function PaletteMenu({ onSelect }) {
    const { t } = useTranslation();
    const [palettes, setPalettes] = useState([]);
    const [activePaletteName, setActivePaletteName] = useState(null);
    const [isOpen, setIsOpen] = useState(false);

    const fetchPalettes = async () => {
        try {
            const [palettesResponse, activeResponse] = await Promise.all([
                fetch("/server/files/get_metadata?metadata_name=custom_color_palettes", { credentials: "include" }),
                fetch("/server/files/get_metadata?metadata_name=active_color_palette", { credentials: "include" })
            ]);

            if (palettesResponse.ok) {
                const data = await palettesResponse.json();
                setPalettes(data.custom_color_palettes || []);
            }

            if (activeResponse.ok) {
                const activeData = await activeResponse.json();
                setActivePaletteName(activeData.active_color_palette || null);
            }
        } catch (err) {
            console.error("Error fetching palettes:", err);
        }
    };

    useEffect(() => {
        if (isOpen) {
            fetchPalettes();
        }
    }, [isOpen]);

    // Listen to openColorPalette event to refresh list when save happens (if needed)
    // Actually PaletteModal will trigger onSave, we could listen to a refresh event or just re-fetch next open
    // Ideally we want to see the new palette immediately if we are the ones who triggered it.
    // But PaletteModal closes itself. 


    const handleAdd = () => {
        window.dispatchEvent(new CustomEvent('openColorPalette', {
            detail: {
                name: `${t('chat.colorPalette.menuTitle', 'palette')}_${palettes.length + 1}`,
                type: 'SEQUENTIAL',
                breaks: []
            }
        }));
        setIsOpen(false);
    };

    const handleEdit = (palette) => {
        window.dispatchEvent(new CustomEvent('openColorPalette', {
            detail: palette
        }));
        setIsOpen(false);
    };

    const handleDelete = async (paletteName) => {
        try {
            const newPalettes = palettes.filter(p => p.name !== paletteName);
            const body = {
                custom_color_palettes: newPalettes
            };
            if (activePaletteName === paletteName) {
                body.active_color_palette = null;
            }

            await fetch("/server/files/set_metadata", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify(body)
            });

            fetchPalettes();
        } catch (err) {
            console.error("Error deleting palette:", err);
        }
    };

    const handleSetActive = async (palette) => {
        try {
            const body = {};
            if (palette) {
                body.active_color_palette = palette.name;
            } else {
                body.active_color_palette = null;
            }

            await fetch("/server/files/set_metadata", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "include",
                body: JSON.stringify(body)
            });
            setActivePaletteName(palette ? palette.name : null);
            if (onSelect) onSelect(palette ? palette.name : null);
        } catch (err) {
            console.error("Error setting active palette:", err);
        }
    };

    return (
        <DialogTrigger isOpen={isOpen} onOpenChange={setIsOpen}>
            <Button className={styles.triggerBtn} aria-label={t("chat.colorPalette.menuTitle")}>
                <div className={styles.colorCircle} style={{
                    background: activePaletteName
                        ? 'conic-gradient(rgb(247, 221, 88), rgb(245, 158, 72), rgb(237, 115, 88), rgb(234, 76, 106), rgb(230, 30, 128), rgb(170, 78, 147), rgb(117, 73, 146), rgb(71, 70, 159), rgb(13, 79, 176), rgb(126 160 255), rgb(37 213 93))'
                        : 'linear-gradient(135deg, rgb(224, 224, 224) 0%, rgb(89 122 137) 100%)'
                }}>
                </div>
            </Button>
            <Popover placement="top" crossOffset={100} className={styles.popover} isNonModal={true}>
                <OverlayArrow className={styles.overlayArrow}>
                    <svg width={12} height={12} viewBox="0 0 12 12">
                        <path d="M0 0 L6 6 L12 0" />
                    </svg>
                </OverlayArrow>
                <Dialog className={styles.dialog}>
                    <div className={styles.header}>
                        <Label>{t("chat.colorPalette.title")}</Label>
                    </div>

                    <div className={styles.listContainer}>
                        <ListBox aria-label={t("chat.colorPalette.menuTitle")} className={styles.listBox} selectionMode="none">
                            {/* Fixed "Let the AI decide" option */}
                            <ListBoxItem textValue={t("chat.colorPalette.aiDecide")} className={`${styles.listItem} ${activePaletteName === null ? styles.activeItem : ''}`}>
                                <div
                                    className={styles.itemContent}
                                    onClick={() => handleSetActive(null)}
                                    style={{ cursor: 'pointer', padding: '6px 0px' }}
                                >
                                    <div className={styles.itemInfo}>
                                        <span className={styles.itemName}>
                                            {t("chat.colorPalette.aiDecide")}
                                        </span>
                                        {activePaletteName === null && (
                                            <div className={styles.activeContainer}>
                                                <span className={styles.activeLabel}>{t("chat.colorPalette.active")}</span>
                                                <IoCheckmark className={styles.activeIcon} />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </ListBoxItem>

                            {palettes.map((palette) => (
                                <ListBoxItem key={palette.name} textValue={palette.name} className={`${styles.listItem} ${activePaletteName === palette.name ? styles.activeItem : ''}`}>
                                    <div
                                        className={styles.itemContent}
                                        onClick={() => handleSetActive(palette)}
                                        style={{ cursor: 'pointer' }}
                                    >
                                        <div className={styles.itemInfo}>
                                            <span className={styles.itemName}>{palette.name}</span>
                                            {activePaletteName === palette.name && (
                                                <div className={styles.activeContainer}>
                                                    <span className={styles.activeLabel}>{t("chat.colorPalette.active")}</span>
                                                    <IoCheckmark className={styles.activeIcon} />
                                                </div>
                                            )}
                                        </div>
                                        <div className={styles.miniPreview}>
                                            {palette.colors && palette.colors.map((c, i) => (
                                                <div key={i} style={{ backgroundColor: c, flex: 1 }} />
                                            ))}
                                        </div>
                                    </div>
                                    <div className={styles.actions}>
                                        <Button onPress={() => handleEdit(palette)} className={styles.actionBtn}>
                                            <IoPencil />
                                        </Button>
                                        <Button onPress={() => handleDelete(palette.name)} className={styles.actionBtn}>
                                            <IoTrash />
                                        </Button>
                                    </div>
                                </ListBoxItem>
                            ))}
                            <ListBoxItem>
                                <Button onPress={handleAdd} className={styles.addBtn} aria-label={t("chat.colorPalette.save")}>
                                    <IoAdd />
                                </Button>
                            </ListBoxItem>
                        </ListBox>
                    </div>
                </Dialog>
            </Popover>
        </DialogTrigger >
    );
}



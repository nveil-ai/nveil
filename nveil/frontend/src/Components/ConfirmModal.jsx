// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { Dialog, Modal, Heading, Button } from 'react-aria-components';
import styles from './ConfirmModal.module.css';

/**
 * Reusable confirmation modal with gradient border + glass backdrop.
 * Drop-in replacement for window.confirm() with consistent app styling.
 */
export default function ConfirmModal({ isOpen, onClose, onConfirm, title, description, confirmLabel, cancelLabel, variant = 'danger' }) {
    if (!isOpen) return null;

    return (
        <Modal isOpen={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
            <div className={styles.modalGlassBg}>
                <Dialog className={styles.dialog} role="alertdialog" style={{ outline: 'none' }}>
                    <div className={styles.content}>
                        <Heading slot="title" className={styles.title}>{title}</Heading>
                        {description && <p className={styles.description}>{description}</p>}
                        <div className={styles.actions}>
                            <Button
                                onPress={onClose}
                                className={styles.cancelButton}
                            >
                                {cancelLabel}
                            </Button>
                            <Button
                                onPress={() => { onConfirm(); onClose(); }}
                                className={`${styles.confirmButton} ${variant === 'danger' ? styles.danger : ''}`}
                                autoFocus
                            >
                                {confirmLabel}
                            </Button>
                        </div>
                    </div>
                </Dialog>
            </div>
        </Modal>
    );
}

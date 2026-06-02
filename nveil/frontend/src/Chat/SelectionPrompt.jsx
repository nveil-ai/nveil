// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
import styles from './SelectionPrompt.module.css';

const SelectionPrompt = ({ prompt, options, focusedIndex, onSelect, onFocusChange, escHint }) => {
    return (
        <div className={styles.selectionContainer}>
            <div className={styles.selectionHeader}>
                <div className={styles.selectionPromptText}>{prompt}</div>
                {escHint && <span className={styles.escHint}>{escHint}</span>}
            </div>
            <div className={styles.optionsList} role="radiogroup">
                {options.map((option, index) => {
                    const isFocused = index === focusedIndex;
                    return (
                        <button
                            key={option.id}
                            role="radio"
                            aria-checked={isFocused}
                            tabIndex={-1}
                            className={`${styles.optionCard} ${isFocused ? styles.optionCardFocused : ''}`}
                            onClick={() => onSelect(option)}
                            onMouseEnter={() => onFocusChange(index)}
                        >
                            <div className={`${styles.radioCircle} ${isFocused ? styles.radioCircleFocused : ''}`} />
                            <div className={styles.optionContent}>
                                <span className={styles.optionLabel}>{option.label}</span>
                                {option.description && (
                                    <span className={styles.optionDescription}>{option.description}</span>
                                )}
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

export default React.memo(SelectionPrompt);

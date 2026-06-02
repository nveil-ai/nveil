// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

// Base react-select styles shared across all Select components.
// `menuPortal` is paired with `menuPortalTarget={document.body}` on the Select
// itself — without portaling, a flipped-up menu can be obscured by a sibling
// card whose parent has a higher z-index in its own stacking context.
export const baseSelectStyles = {
    menu: (base) => ({ ...base, backgroundColor: "#2f2e2e", borderRadius: "8px" }),
    menuPortal: (base) => ({ ...base, zIndex: 9999 }),
    indicatorSeparator: () => ({ display: 'none' }),
    singleValue: (base) => ({ ...base, color: "white" }),
    input: (base) => ({ ...base, color: "white" }),
    menuList: (base) => ({ ...base, paddingBottom: "4px", paddingTop: "4px", borderRadius: "8px" }),
    option: (base, state) => ({
        ...base,
        backgroundColor: state.isFocused ? 'rgb(23 130 195)' : 'transparent',
        color: 'white',
        cursor: 'pointer',
        ':active': { backgroundColor: '#4c4a4a' },
        padding: '8px 12px',
        borderRadius: '10px',
        margin: '4px 4px',
        width: "auto",
    }),
};

export const darkSelectTheme = (theme) => ({
    ...theme,
    colors: { ...theme.colors, neutral0: '#2f2e2e', primary: 'white' },
});

// Helper to merge base styles with per-instance overrides
export const mergeSelectStyles = (overrides = {}) => {
    const merged = { ...baseSelectStyles };
    for (const key of Object.keys(overrides)) {
        if (baseSelectStyles[key]) {
            // Pass the result of base styles as `base` to the override,
            // so overrides build on top of our dark theme, not react-select defaults.
            merged[key] = (base, state) => {
                const styled = baseSelectStyles[key](base, state);
                return overrides[key](styled, state);
            };
        } else {
            merged[key] = overrides[key];
        }
    }
    return merged;
};

// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-FileContributor: Clément Baraille
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useTranslation } from 'react-i18next';
import SliderControl from './controls/SliderControl';
import SelectControl from './controls/SelectControl';
import SwitchControl from './controls/SwitchControl';
import ButtonControl from './controls/ButtonControl';
import WidgetGroup from './controls/WidgetGroup';
import InfoPanel from './controls/InfoPanel';
import SparklinePreview from './controls/SparklinePreview';
import ClippingControl from './controls/ClippingControl';

function evalVisibility(condition, getValue) {
    if (!condition) return true;
    if (Array.isArray(condition.or)) {
        return condition.or.some(c => evalVisibility(c, getValue));
    }
    const { key, op, value } = condition;
    const current = getValue(key);
    switch (op) {
        case '===': return current === value;
        case '!==': return current !== value;
        default: return true;
    }
}

// Best-effort humanization for widget label keys that don't yet have an
// i18n entry. Splits CamelCase, snake_case and kebab-case into words,
// preserves ALLCAPS acronyms, and collapses any leftover runs of
// whitespace. Used as the fallback for t() so untranslated keys like
// "DecreasingByValue" render as "Decreasing By Value" instead of a raw
// run-on identifier.
function humanizeLabelKey(key) {
    if (typeof key !== 'string' || !key) return key;
    return key
        .replace(/[_-]+/g, ' ')
        .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
        .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
        .replace(/\s+/g, ' ')
        .trim();
}

export default function WidgetRenderer({ descriptors, getValue, setValue }) {
    const { t } = useTranslation();
    if (!descriptors?.length) return null;

    // Resolve label through i18n — raw key from Python, translated in React.
    // Missing entries fall back to a humanized split of the CamelCase key.
    const label = (key) => t('widgets.' + key, humanizeLabelKey(key));

    // Translate select-option titles the same way so values like
    // "DecreasingByValue" pick up the shared CamelCase-split fallback.
    const translateItems = (items) =>
        (items || []).map(it => ({ ...it, title: label(it.title) }));

    return descriptors.map((desc, i) => {
        if (desc.visible_when && !evalVisibility(desc.visible_when, getValue)) {
            return null;
        }

        // Position-based React key — multiple marks can emit the same desc.key
        // (e.g. UniGrid and Contour both declare "resolution"), and duplicate
        // sibling keys break React reconciliation (zombie DOM across rerenders).
        // Both sliders still write to the shared state via setValue(desc.key, ...).
        const key = `${i}-${desc.key || desc.type}`;

        switch (desc.type) {
            case 'info':
                return <InfoPanel key={key} title={label(desc.title)} text={label(desc.text)} />;

            case 'group':
                return (
                    <WidgetGroup key={key} label={label(desc.label)} icon={desc.icon} expanded={desc.expanded}>
                        <WidgetRenderer descriptors={desc.children} getValue={getValue} setValue={setValue} />
                    </WidgetGroup>
                );

            case 'sparkline':
                return (
                    <SparklinePreview
                        key={key}
                        values={getValue(desc.key) || []}
                        colors={getValue(desc.gradient_key) || []}
                        height={desc.height || 120}
                    />
                );

            case 'slider':
                return (
                    <SliderControl
                        key={key}
                        label={label(desc.label)}
                        icon={desc.icon}
                        min={desc.min}
                        max={desc.max}
                        step={desc.step}
                        value={getValue(desc.key) ?? desc.default}
                        defaultValue={desc.default}
                        ticks={desc.ticks}
                        onChange={(val) => setValue(desc.key, val, desc.set_on_drag ? { [desc.set_on_drag]: true } : undefined)}
                        onDragEnd={desc.set_on_drag ? () => setValue(desc.set_on_drag, false) : undefined}
                    />
                );

            case 'select':
                return (
                    <SelectControl
                        key={key}
                        label={label(desc.label)}
                        icon={desc.icon}
                        items={translateItems(desc.items)}
                        value={getValue(desc.key) ?? desc.default}
                        onChange={(val) => setValue(desc.key, val)}
                    />
                );

            case 'switch':
                return (
                    <SwitchControl
                        key={key}
                        label={label(desc.label)}
                        icon={desc.icon}
                        value={getValue(desc.key) ?? desc.default}
                        onChange={(val) => setValue(desc.key, val)}
                    />
                );

            case 'button':
                return (
                    <ButtonControl
                        key={key}
                        label={label(desc.label)}
                        icon={desc.icon}
                        variant={desc.variant}
                        disabled={desc.disabled_when ? evalVisibility(desc.disabled_when, getValue) : false}
                        onClick={() => setValue(desc.trigger_key, Date.now())}
                    />
                );

            case 'text':
                return (
                    <div key={key} style={{
                        fontSize: '0.82rem',
                        color: desc.muted ? '#888' : '#aaa',
                        padding: '4px 0',
                        fontFamily: desc.mono ? 'monospace' : 'inherit',
                        lineHeight: 1.4,
                    }}>
                        {desc.state_key ? (getValue(desc.state_key) || desc.fallback || '') : label(desc.content)}
                    </div>
                );

            case 'clipping':
                return (
                    <ClippingControl
                        key={key}
                        label={label(desc.label)}
                        getValue={getValue}
                        setValue={setValue}
                    />
                );

            case 'divider':
                return <hr key={key} style={{ border: 'none', borderTop: '1px solid rgba(255,255,255,0.04)', margin: '8px 0' }} />;

            default:
                return null;
        }
    });
}

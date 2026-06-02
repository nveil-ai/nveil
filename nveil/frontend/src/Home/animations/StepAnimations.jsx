// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useEffect, useRef } from 'react';

import uploadHtml from './upload.html?raw';
import describeHtml from './describe.html?raw';
import visualizeHtml from './visualize.html?raw';

import './upload.css';
import './describe.css';
import './visualize.css';

import { init as initUpload } from './upload.js';
import { init as initDescribe } from './describe.js';
import { init as initVisualize } from './visualize.js';

const WRAPPER_STYLE = {
    display: 'flex',
    justifyContent: 'center',
    overflow: 'hidden',
    background: '#FFFFFF',
    height: 520,
    fontFamily: 'Inter, sans-serif',
    width: '100%',
};

function StepAnimation({ className, markup, init }) {
    const ref = useRef(null);
    useEffect(() => {
        // The markup lands via dangerouslySetInnerHTML in the same commit, so
        // the root element is already in the DOM by the time this effect runs.
        //
        // Defers init() twice to stay off the critical rendering path:
        //   1. IntersectionObserver — only run init() once the step is in
        //      view. The three steps (upload/describe/visualize) stack
        //      vertically; running all three on mount burns CPU on content
        //      users may never scroll to and compounds main-thread blocking.
        //   2. requestIdleCallback — once visible, wait for main-thread idle
        //      so the ~300ms of SVG setup doesn't contribute to TBT between
        //      FCP and TTI.
        // prefers-reduced-motion: the first scene is already rendered
        // statically by the markup, so skipping init() means no animation
        // loop — the user still sees meaningful content.
        const el = ref.current;
        if (!el) return;

        const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
        if (prefersReducedMotion) return;

        let cancelled = false;
        let idleHandle = null;

        const runInit = () => {
            if (cancelled) return;
            if ('requestIdleCallback' in window) {
                idleHandle = window.requestIdleCallback(init, { timeout: 2000 });
            } else {
                idleHandle = window.setTimeout(init, 300);
            }
        };

        const io = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    io.disconnect();
                    runInit();
                }
            },
            { rootMargin: '100px' },
        );
        io.observe(el);

        return () => {
            cancelled = true;
            io.disconnect();
            if (idleHandle != null) {
                if ('cancelIdleCallback' in window) window.cancelIdleCallback(idleHandle);
                else window.clearTimeout(idleHandle);
            }
        };
    }, [init]);
    return (
        <div
            ref={ref}
            className={className}
            style={WRAPPER_STYLE}
            dangerouslySetInnerHTML={{ __html: markup }}
        />
    );
}

export function UploadStep() {
    return (
        <StepAnimation
            className="anim-upload"
            markup={uploadHtml}
            init={initUpload}
        />
    );
}

export function DescribeStep() {
    return (
        <StepAnimation
            className="anim-describe"
            markup={describeHtml}
            init={initDescribe}
        />
    );
}

export function VisualizeStep() {
    return (
        <StepAnimation
            className="anim-visuals"
            markup={visualizeHtml}
            init={initVisualize}
        />
    );
}

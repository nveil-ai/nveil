// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import React from 'react';
import { Helmet } from 'react-helmet-async';
import i18n from '../i18n';

export default function SEO({
    title,
    description,
    name = "NVEIL",
    type = "website",
    url,
    image = "https://app.nveil.com/icons/nveil-512.png",
    structuredData,
    robots,
    iconPng48 = "/icons/nveil-48.png",
    iconPng96 = "/icons/nveil-96.png",
    iconAppleTouch180 = "/icons/nveil-180.png",
    manifestUrl = "/manifest.json",
    siteUrl = "https://app.nveil.com/",
    orgUrl = "https://nveil.com/",
    logo = "https://app.nveil.com/icons/nveil-192.png"
}) {
    const defaultTitle = "NVEIL – No-Code AI Data Visualization | Auditable Insights";
    const defaultDescription = "Turn your data into production-ready visualizations in seconds. Reliable no-code AI with auditable, deterministic results — no hallucinations.";

    const metaTitle = title ? `${title}` : defaultTitle;
    const metaDescription = description || defaultDescription;
    const lang = (i18n?.resolvedLanguage || i18n?.language || 'en').split('-')[0];

    const resolvedUrl = url || (() => {
        // Enforce production domain for canonical URLs, ignoring localhost/staging origins
        const origin = siteUrl.endsWith('/') ? siteUrl.slice(0, -1) : siteUrl;
        // Strip query params (like kedro args) from canonical URL to consolidate ranking
        const path = typeof window !== 'undefined' ? window.location.pathname : '/';
        return `${origin}${path}`;
    })();

    const ogLocale = lang === 'fr' ? 'fr_FR' : 'en_US';

    const mergedStructuredData = (() => {
        const baseGraph = [
            {
                "@type": "Organization",
                "@id": `${orgUrl}#organization`,
                "name": name,
                "url": orgUrl,
                "logo": logo
            },
            {
                "@type": "WebSite",
                "@id": `${siteUrl}#website`,
                "url": siteUrl,
                "name": name,
                "publisher": { "@id": `${orgUrl}#organization` }
            },
            {
                "@type": "WebApplication",
                "@id": `${siteUrl}#webapp`,
                "name": name,
                "url": siteUrl,
                "description": defaultDescription,
                "applicationCategory": "ScientificApplication",
                "operatingSystem": "Web",
                "creator": { "@id": `${orgUrl}#organization` }
            }
        ];

        if (!structuredData) {
            return { "@context": "https://schema.org", "@graph": baseGraph };
        }

        // Accept: single object, array of objects, or { @graph: [...] }.
        const incoming = Array.isArray(structuredData)
            ? structuredData
            : (structuredData?.['@graph'] ? structuredData['@graph'] : [structuredData]);

        // Avoid duplicating base nodes if caller included them.
        const graph = [...baseGraph, ...incoming.filter(Boolean)];
        return { "@context": "https://schema.org", "@graph": graph };
    })();

    return (
        <Helmet htmlAttributes={{ lang }}>
            {/* Standard metadata */}
            <title>{metaTitle}</title>
            <meta name="description" content={metaDescription} />
            <meta name="robots" content={robots || "index, follow"} />
            <link rel="canonical" href={resolvedUrl} />
            {/* Icons */}
            <link rel="icon" href={iconPng48} type="image/png" sizes="48x48" />
            <link rel="icon" href={iconPng96} type="image/png" sizes="96x96" />
            <link rel="apple-touch-icon" href={iconAppleTouch180} sizes="180x180" />
            <link rel="manifest" href={manifestUrl} />

            {/* Open Graph / Facebook */}
            <meta property="og:type" content={type} />
            <meta property="og:url" content={resolvedUrl} />
            <meta property="og:title" content={metaTitle} />
            <meta property="og:description" content={metaDescription} />
            <meta property="og:image" content={image} />
            <meta property="og:site_name" content={name} />
            <meta property="og:locale" content={ogLocale} />

            {/* Twitter */}
            <meta name="twitter:card" content="summary_large_image" />
            <meta name="twitter:creator" content={name} />
            <meta name="twitter:title" content={metaTitle} />
            <meta name="twitter:description" content={metaDescription} />
            <meta name="twitter:image" content={image} />

            {/* Structured Data (JSON-LD) */}
            <script type="application/ld+json">
                {JSON.stringify(mergedStructuredData)}
            </script>
        </Helmet>
    );
}

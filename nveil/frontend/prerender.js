// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import puppeteer from 'puppeteer';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROUTES = ['/', '/explore', '/feedback', '/plan'];
const DIST_DIR = path.join(__dirname, 'dist');
const SNAPSHOTS_DIR = path.join(DIST_DIR, 'snapshots');

// Patterns to block during prerendering — auth, API, analytics, WebSocket
const BLOCKED_PATTERNS = [
    '/server/auth/',
    '/api/',
    '/ws/',
    'google-analytics',
    'googletagmanager',
    'gtag',
    'reddit.com/pixel',
];

async function prerender() {
    console.log('🚀 Starting pre-rendering...');
    const browser = await puppeteer.launch({
        headless: "new",
        ignoreHTTPSErrors: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox', '--ignore-certificate-errors']
    });

    for (const route of ROUTES) {
        const page = await browser.newPage();

        await page.setUserAgent('Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)');
        await page.setViewport({ width: 1280, height: 800 });

        // Signal to the SPA that it's being pre-rendered — skip auth, analytics, WS
        await page.evaluateOnNewDocument(() => {
            window.__PRERENDERING = true;
        });

        // Block auth/API/analytics requests to avoid 401/503 errors and junk DB entries
        await page.setRequestInterception(true);
        page.on('request', (req) => {
            const url = req.url();
            if (BLOCKED_PATTERNS.some(p => url.includes(p))) {
                req.abort('aborted');
            } else {
                req.continue();
            }
        });

        // Suppress console noise from the headless browser
        page.on('console', () => {});
        page.on('pageerror', () => {});

        const targetUrl = `https://localhost:8000${route}`;

        try {
            console.log(`  Rendering ${route}...`);
            await page.goto(targetUrl, { waitUntil: 'networkidle0', timeout: 30000 });

            // Wait for React + Helmet to settle
            await new Promise(r => setTimeout(r, 1500));

            const html = await page.content();

            const routePath = route === '/' ? 'index.html' : `${route.substring(1)}/index.html`;
            const outputPath = path.join(SNAPSHOTS_DIR, routePath);
            const outputDir = path.dirname(outputPath);

            if (!fs.existsSync(outputDir)) {
                fs.mkdirSync(outputDir, { recursive: true });
            }

            if (fs.existsSync(outputPath)) {
                try {
                    fs.unlinkSync(outputPath);
                } catch (e) {
                    console.warn(`  ⚠️ Could not delete ${outputPath}: ${e.message}`);
                }
            }

            fs.writeFileSync(outputPath, html);
            console.log(`  ✅ ${outputPath}`);
        } catch (e) {
            console.error(`  ❌ Failed to render ${route}:`, e.message);
        } finally {
            await page.close();
        }
    }

    await browser.close();
    console.log('✨ Pre-rendering complete!');
}

prerender();

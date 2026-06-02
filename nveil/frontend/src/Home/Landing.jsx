// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../Auth/AuthContext';
import SEO from '../Components/SEO';
import { UploadStep, DescribeStep, VisualizeStep } from './animations/StepAnimations';
import styles from './Landing.module.css';

const FEATURES = [
    { key: 'ai' },
    { key: 'auditable' },
    { key: 'vizTypes' },
];

const STEPS = [
    { key: 'upload', Animation: UploadStep },
    { key: 'describe', Animation: DescribeStep },
    { key: 'visualize', Animation: VisualizeStep },
];

const USE_CASES = [
    {
        key: 'research',
        gradId: 'sciGrad',
        gradStops: [['0%', '#9662FE'], ['100%', '#C49BFF']],
        circleFill: '#9662FE',
        icon: (
            <>
                <path d="M30 18V30L20 50C19 52 20.5 54 23 54H49C51.5 54 53 52 52 50L42 30V18" stroke="url(#sciGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <line x1="28" y1="18" x2="44" y2="18" stroke="url(#sciGrad)" strokeWidth="2" strokeLinecap="round"/>
                <path d="M24 46L30 36H42L48 46C49 48 48 50 46 50H26C24 50 23 48 24 46Z" fill="#9662FE" fillOpacity="0.2"/>
                <circle cx="32" cy="43" r="2" fill="#9662FE" fillOpacity="0.5"/>
                <circle cx="40" cy="40" r="1.5" fill="#C49BFF" fillOpacity="0.5"/>
                <circle cx="36" cy="46" r="1" fill="#C49BFF" fillOpacity="0.5"/>
                <circle cx="54" cy="22" r="1.5" fill="#9662FE" fillOpacity="0.4"/>
                <circle cx="57" cy="26" r="1" fill="#C49BFF" fillOpacity="0.3"/>
            </>
        ),
    },
    {
        key: 'business',
        gradId: 'bizGrad',
        gradStops: [['0%', '#00bfa5'], ['100%', '#9662FE']],
        circleFill: '#00bfa5',
        icon: (
            <>
                <rect x="18" y="38" width="8" height="16" rx="2" fill="#00bfa5" fillOpacity="0.5"/>
                <rect x="28" y="30" width="8" height="24" rx="2" fill="#9662FE" fillOpacity="0.5"/>
                <rect x="38" y="24" width="8" height="30" rx="2" fill="#C49BFF" fillOpacity="0.5"/>
                <rect x="48" y="20" width="8" height="34" rx="2" fill="#C49BFF" fillOpacity="0.5"/>
                <polyline points="22,36 32,28 42,22 52,18" stroke="url(#bizGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <path d="M50 16L54 18L50 20" stroke="url(#bizGrad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
            </>
        ),
    },
    {
        key: 'education',
        gradId: 'eduGrad',
        gradStops: [['0%', '#C49BFF'], ['100%', '#f472b6']],
        circleFill: '#C49BFF',
        icon: (
            <>
                <polygon points="36,20 16,30 36,40 56,30" fill="none" stroke="url(#eduGrad)" strokeWidth="2" strokeLinejoin="round"/>
                <polygon points="36,20 16,30 36,40 56,30" fill="#C49BFF" fillOpacity="0.12"/>
                <line x1="56" y1="30" x2="56" y2="44" stroke="url(#eduGrad)" strokeWidth="1.5" strokeLinecap="round"/>
                <circle cx="56" cy="46" r="2" fill="#f472b6" fillOpacity="0.5"/>
                <path d="M22 36V48C22 48 29 46 36 48C43 46 50 48 50 48V36" stroke="url(#eduGrad)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <line x1="36" y1="40" x2="36" y2="48" stroke="url(#eduGrad)" strokeWidth="1" strokeOpacity="0.5"/>
                <circle cx="22" cy="22" r="1.5" fill="#C49BFF" fillOpacity="0.4"/>
                <circle cx="50" cy="18" r="1" fill="#f472b6" fillOpacity="0.3"/>
            </>
        ),
    },
    {
        key: 'geographic',
        gradId: 'geoGrad',
        gradStops: [['0%', '#fbbf24'], ['100%', '#00bfa5']],
        circleFill: '#fbbf24',
        icon: (
            <>
                <circle cx="36" cy="36" r="18" stroke="url(#geoGrad)" strokeWidth="1.8" fill="none"/>
                <ellipse cx="36" cy="36" rx="9" ry="18" stroke="url(#geoGrad)" strokeWidth="1" strokeOpacity="0.4" fill="none"/>
                <line x1="18" y1="36" x2="54" y2="36" stroke="url(#geoGrad)" strokeWidth="1" strokeOpacity="0.4"/>
                <ellipse cx="36" cy="28" rx="16" ry="4" stroke="url(#geoGrad)" strokeWidth="0.8" strokeOpacity="0.3" fill="none"/>
                <ellipse cx="36" cy="44" rx="16" ry="4" stroke="url(#geoGrad)" strokeWidth="0.8" strokeOpacity="0.3" fill="none"/>
                <circle cx="30" cy="30" r="2.5" fill="#fbbf24" fillOpacity="0.6"/>
                <circle cx="42" cy="38" r="2.5" fill="#00bfa5" fillOpacity="0.6"/>
                <circle cx="34" cy="44" r="2" fill="#9662FE" fillOpacity="0.5"/>
                <line x1="30" y1="30" x2="42" y2="38" stroke="#fbbf24" strokeWidth="0.8" strokeOpacity="0.3" strokeDasharray="2"/>
                <line x1="42" y1="38" x2="34" y2="44" stroke="#00bfa5" strokeWidth="0.8" strokeOpacity="0.3" strokeDasharray="2"/>
            </>
        ),
    },
    {
        // Data Science & Engineering — scatter + trend + neural nodes
        key: 'engineering',
        gradId: 'dsGrad',
        gradStops: [['0%', '#7B4ED4'], ['100%', '#00bfa5']],
        circleFill: '#7B4ED4',
        icon: (
            <>
                <polyline points="18,52 26,42 34,46 42,30 50,34 56,22" stroke="url(#dsGrad)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                <circle cx="22" cy="48" r="2.4" fill="#7B4ED4" fillOpacity="0.65"/>
                <circle cx="30" cy="40" r="2.4" fill="#9662FE" fillOpacity="0.65"/>
                <circle cx="38" cy="36" r="2.4" fill="#C49BFF" fillOpacity="0.65"/>
                <circle cx="46" cy="28" r="2.4" fill="#00bfa5" fillOpacity="0.65"/>
                <circle cx="54" cy="22" r="2.4" fill="#00bfa5" fillOpacity="0.85"/>
                <line x1="22" y1="48" x2="38" y2="36" stroke="#9662FE" strokeWidth="0.8" strokeOpacity="0.35" strokeDasharray="2 2"/>
                <line x1="30" y1="40" x2="46" y2="28" stroke="#9662FE" strokeWidth="0.8" strokeOpacity="0.35" strokeDasharray="2 2"/>
                <circle cx="20" cy="22" r="1.4" fill="#C49BFF" fillOpacity="0.4"/>
                <circle cx="58" cy="48" r="1.2" fill="#00bfa5" fillOpacity="0.35"/>
            </>
        ),
    },
];

const DEMO_VIDEO_ID = 'uJRN7De0fpk';

export default function Landing() {
    const { t } = useTranslation();
    const { setShowAuthModal, createGuestSession } = useAuth();
    const navigate = useNavigate();
    const [demoLoading, setDemoLoading] = useState(false);

    const handleDemo = async () => {
        if (demoLoading) return;
        setDemoLoading(true);
        try {
            const ok = await createGuestSession();
            if (ok) {
                navigate('/');
            }
        } finally {
            setDemoLoading(false);
        }
    };

    return (
        <main className={styles.page}>
            <SEO
                title={t('seo.homeTitle')}
                description={t('seo.homeDescription')}
            />
            <div className={styles.auroraAccent} aria-hidden="true" />

            {/* Hero */}
            <section className={styles.hero}>
                <h1 className={styles.headline}>
                    {t('landing.heroTitle')}
                    <br />
                    <span className={styles.headlineAccent}>
                        {t('landing.heroAccent')}
                    </span>
                </h1>
                <p className={styles.subheadline}>
                    {t('landing.heroSubtitle')}
                </p>
                <div className={styles.heroCtas}>
                    <button
                        className={styles.ctaPrimary}
                        onClick={() => setShowAuthModal(true)}
                    >
                        {t('landing.ctaTry')}
                    </button>
                    <button
                        className={`${styles.ctaGhost} ${styles.ctaGhostPulse}`}
                        onClick={handleDemo}
                        disabled={demoLoading}
                    >
                        {t('landing.ctaDemo')}
                    </button>
                    <button
                        className={styles.ctaGhost}
                        onClick={() => navigate('/explore')}
                    >
                        {t('landing.ctaExamples')}
                    </button>
                </div>
            </section>

            {/* How it works */}
            <section className={styles.section} aria-labelledby="steps-heading">
                <h2 id="steps-heading" className={styles.sectionTitle}>
                    {t('landing.stepsTitle')}
                </h2>
                <div className={styles.stepsColumn}>
                    {STEPS.map(({ key, Animation }, i) => (
                        <div key={key} className={styles.stepBlock} style={{ '--i': i }}>
                            <div className={styles.stepMarker} aria-hidden="true">
                                <span className={styles.stepMarkerNumber}>
                                    {String(i + 1).padStart(2, '0')}
                                </span>
                                <span className={styles.stepMarkerRule} />
                            </div>
                            <div className={styles.stepAnimationWrap}>
                                <Animation />
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Features */}
            <section className={styles.section} aria-labelledby="features-heading">
                <h2 id="features-heading" className={styles.sectionTitle}>
                    {t('landing.featuresTitle')}
                </h2>
                <div className={styles.featureGrid}>
                    {FEATURES.map((f, i) => (
                        <article
                            key={f.key}
                            className={styles.featureCard}
                            style={{ '--i': i }}
                        >
                            <div className={styles.featureGlow} />
                            <div className={styles.featureInner}>
                                <h3 className={styles.featureLabel}>
                                    {t(`landing.feature.${f.key}.title`)}
                                </h3>
                                <p className={styles.featureDesc}>
                                    {t(`landing.feature.${f.key}.desc`)}
                                </p>
                            </div>
                        </article>
                    ))}
                </div>
            </section>

            {/* Explore preview — replaces the literal "30+ viz types" cards */}
            <section className={styles.section} aria-labelledby="explore-heading">
                <h2 id="explore-heading" className={styles.sectionTitle}>
                    {t('landing.exploreTitle')}
                </h2>
                <p className={styles.sectionSubtitle}>
                    {t('landing.exploreSubtitle')}
                </p>
                <button
                    type="button"
                    className={styles.explorePreview}
                    onClick={() => navigate('/explore')}
                    aria-label={t('landing.exploreCta')}
                >
                    <img
                        src="/explore-preview.webp"
                        alt=""
                        className={styles.explorePreviewImage}
                        loading="lazy"
                    />
                    <div className={styles.explorePreviewFade} aria-hidden="true" />
                    <span className={styles.explorePreviewCta}>
                        {t('landing.exploreCta')}
                    </span>
                </button>
            </section>

            {/* Video demo */}
            <section className={styles.section} aria-labelledby="video-heading">
                <h2 id="video-heading" className={styles.sectionTitle}>
                    {t('landing.videoTitle')}
                </h2>
                <p className={styles.sectionSubtitle}>
                    {t('landing.videoSubtitle')}
                </p>
                <div className={styles.videoFrame}>
                    <iframe
                        src={`https://www.youtube-nocookie.com/embed/${DEMO_VIDEO_ID}?autoplay=1&mute=1&loop=1&playlist=${DEMO_VIDEO_ID}&controls=1&modestbranding=1&rel=0&playsinline=1`}
                        title="NVEIL demo"
                        loading="lazy"
                        allow="autoplay; encrypted-media; picture-in-picture"
                        allowFullScreen
                    />
                </div>
            </section>

            {/* Use cases */}
            <section className={styles.section} aria-labelledby="usecases-heading">
                <h2 id="usecases-heading" className={styles.sectionTitle}>
                    {t('landing.useCasesTitle')}
                </h2>
                <div className={styles.useCaseGrid}>
                    {USE_CASES.map((uc, i) => (
                        <article
                            key={uc.key}
                            className={styles.useCaseCard}
                            style={{ '--i': i }}
                        >
                            <div className={styles.useCaseIcon}>
                                <svg viewBox="0 0 72 72" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <defs>
                                        <linearGradient id={uc.gradId} x1="0%" y1="0%" x2="100%" y2="100%">
                                            {uc.gradStops.map(([offset, color]) => (
                                                <stop key={offset} offset={offset} style={{ stopColor: color, stopOpacity: 1 }} />
                                            ))}
                                        </linearGradient>
                                    </defs>
                                    <circle cx="36" cy="36" r="34" fill={uc.circleFill} fillOpacity="0.06" stroke={`url(#${uc.gradId})`} strokeWidth="1" strokeOpacity="0.3"/>
                                    {uc.icon}
                                </svg>
                            </div>
                            <h3 className={styles.useCaseTitle}>
                                {t(`landing.useCase.${uc.key}.title`)}
                            </h3>
                            <p className={styles.useCaseDesc}>
                                {t(`landing.useCase.${uc.key}.desc`)}
                            </p>
                        </article>
                    ))}
                </div>
            </section>

            {/* Bottom CTA */}
            <section className={styles.bottomCta}>
                <h2 className={styles.bottomCtaTitle}>
                    {t('landing.bottomCtaTitle')}
                </h2>
                <button
                    className={styles.ctaPrimary}
                    onClick={() => setShowAuthModal(true)}
                >
                    {t('landing.ctaTry')}
                </button>
            </section>
        </main>
    );
}

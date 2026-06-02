// SPDX-FileCopyrightText: 2025 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { Dialog, Modal, Heading, Button } from 'react-aria-components';
import { useTranslation, Trans } from 'react-i18next';
import { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import styles from './WelcomeModal.module.css';

// --- Overlay spotlight component ---
function SpotlightOverlay({ targetId, onPositionChange }) {
  const [rect, setRect] = useState(null);

  const updateRect = () => {
    let element = null;

    if (typeof targetId === 'object') {
      if (targetId.virtual === 'right-sidebar') {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        element = {
          getBoundingClientRect: () => ({
            top: 0, left: viewportWidth - 70, width: 70,
            height: viewportHeight, right: viewportWidth, bottom: viewportHeight
          })
        };
      } else if (targetId.iframeId) {
        const iframe = document.getElementById(targetId.iframeId);
        if (iframe && iframe.contentDocument) {
          const innerEl = iframe.contentDocument.querySelector(targetId.selector);
          if (innerEl) {
            const iframeRect = iframe.getBoundingClientRect();
            const innerRect = innerEl.getBoundingClientRect();
            element = {
              getBoundingClientRect: () => ({
                top: iframeRect.top + innerRect.top, left: iframeRect.left + innerRect.left,
                width: innerRect.width, height: innerRect.height, padding: 5,
                bottom: iframeRect.top + innerRect.top + innerRect.height,
                right: iframeRect.left + innerRect.left + innerRect.width,
              })
            };
          }
        }
      } else if (targetId.shadowHostSelector) {
        const host = document.querySelector(targetId.shadowHostSelector);
        if (host && host.shadowRoot) {
          element = host.shadowRoot.querySelector(targetId.selector);
        }
      } else if (targetId.selector) {
        element = document.querySelector(targetId.selector);
      }
    } else {
      element = document.getElementById(targetId);
    }

    if (element) {
      const r = element.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      const newRect = { top: r.top, left: r.left, width: r.width, height: r.height, right: r.right, bottom: r.bottom };
      setRect(newRect);
      onPositionChange && onPositionChange(newRect);
    } else {
      setRect(null);
      onPositionChange && onPositionChange(null);
    }
  };

  useEffect(() => {
    updateRect();
    const handleResize = () => updateRect();
    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', updateRect, true);
    const interval = setInterval(updateRect, 500);
    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', updateRect, true);
      clearInterval(interval);
    };
  }, [targetId]);

  if (!rect) return null;

  return (
    <>
      <div className={styles.spotlightDim} style={{ top: 0, left: 0, width: '100vw', height: rect.top }} />
      <div className={styles.spotlightDim} style={{ top: rect.top, left: 0, width: rect.left, height: rect.height }} />
      <div className={styles.spotlightDim} style={{ top: rect.top, left: rect.right, right: 0, height: rect.height }} />
      <div className={styles.spotlightDim} style={{ top: rect.bottom, left: 0, width: '100vw', bottom: 0 }} />
      <div style={{
        position: 'absolute', top: rect.top, left: rect.left,
        width: rect.width, height: rect.height,
        boxShadow: '0 0 0 2px rgba(255, 255, 255, 0.8), 0 0 20px rgba(255, 255, 255, 0.4)',
        borderRadius: '4px', pointerEvents: 'none', zIndex: 10002
      }} />
    </>
  );
}

// --- Route transition overlay ---
function RouteTransition({ targetLabel, visible }) {
  if (!visible) return null;
  return (
    <div className={styles.routeTransition}>
      <div className={styles.routeTransitionContent}>
        <div className={styles.routeTransitionSpinner} />
        <span>{targetLabel}</span>
      </div>
    </div>
  );
}

export default function WelcomeModal({ open, onClose }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState(0);
  const [modalPos, setModalPos] = useState(null);
  const [transitioning, setTransitioning] = useState(false);
  const [transitionLabel, setTransitionLabel] = useState('');
  const waitTimerRef = useRef(null);

  useEffect(() => {
    if (open) setStep(0);
  }, [open]);

  useEffect(() => {
    const currentStepData = step > 0 ? TUTORIAL_STEPS[step - 1] : null;
    if (currentStepData?.targetId?.shadowHostSelector === 'deep-chat') {
      try {
        document.querySelector('deep-chat').shadowRoot.querySelectorAll(".history-show-viz")[0].scrollIntoView({ block: "center", inline: "nearest" });
      } catch (e) { }
    }
  }, [step]);

  const TUTORIAL_STEPS = [
    {
      targetId: { selector: 'deep-chat, #chat-panel [class*="chatContainer"]' },
      title: t('tutorial.step1.title'),
      content: t('tutorial.step1.content'),
      position: 'right',
      route: '/'
    },
    {
      targetId: 'chat-upload-button',
      title: t('tutorial.stepUpload.title'),
      content: t('tutorial.stepUpload.content'),
      position: 'top-right',
      route: '/'
    },
    {
      targetId: { shadowHostSelector: 'deep-chat', selector: '.history-show-viz' },
      title: t('tutorial.step25.title'),
      content: t('tutorial.step25.content'),
      position: 'right',
      route: '/'
    },
    {
      targetId: { shadowHostSelector: 'deep-chat', selector: '.history-export-dashboard' },
      title: t('tutorial.stepExportDashboard.title'),
      content: t('tutorial.stepExportDashboard.content'),
      position: 'right',
      route: '/'
    },
    {
      targetId: 'viz-panel',
      title: t('tutorial.step3.title'),
      content: t('tutorial.step3.content'),
      position: 'left',
      route: '/'
    },
    {
      targetId: 'nav-explore',
      title: t('tutorial.step4.title'),
      content: t('tutorial.step4.content'),
      position: 'bottom',
      route: '/explore',
      routeLabel: 'Explore'
    },
    {
      targetId: 'nav-dashboards',
      title: t('tutorial.stepDashboard.title'),
      content: t('tutorial.stepDashboard.content'),
      position: 'bottom',
      route: '/dashboards',
      routeLabel: 'Dashboards'
    },
    {
      targetId: { selector: 'deep-chat, #chat-panel [class*="chatContainer"]' },
      title: t('tutorial.stepFinish.title'),
      content: t('tutorial.stepFinish.content'),
      position: 'right',
      route: '/',
      routeLabel: 'Home'
    }
  ];

  const waitForTarget = useCallback((stepData, callback) => {
    let attempts = 0;
    const maxAttempts = 30;

    const check = () => {
      attempts++;
      const targetId = stepData.targetId;
      let found = false;

      if (typeof targetId === 'object') {
        if (targetId.shadowHostSelector) {
          const host = document.querySelector(targetId.shadowHostSelector);
          found = host?.shadowRoot?.querySelector(targetId.selector);
        } else if (targetId.selector) {
          found = document.querySelector(targetId.selector);
        }
      } else {
        found = document.getElementById(targetId);
      }

      if (found || attempts >= maxAttempts) {
        callback();
      } else {
        waitTimerRef.current = setTimeout(check, 100);
      }
    };
    check();
  }, []);

  useEffect(() => {
    return () => {
      if (waitTimerRef.current) clearTimeout(waitTimerRef.current);
    };
  }, []);

  const handleSpotlightUpdate = (rect) => {
    if (!rect) return;
    const currentStepData = TUTORIAL_STEPS[step - 1];
    const preferredPos = currentStepData?.position || 'bottom';
    let top = 0, left = 0;
    const margin = 20;

    if (preferredPos === 'center') {
      setModalPos(null);
      return;
    }

    const tooltipW = 400;
    const tooltipH = 200;
    const [primary, secondary] = preferredPos.split('-');

    // Primary axis: which side of the target the tooltip sits on
    // Secondary axis: which direction it shifts along the other axis
    // The tooltip's corner closest to the target is the pivot point.
    if (primary === 'top') {
      top = rect.top - tooltipH - margin;
      left = secondary === 'right' ? rect.right + margin
           : secondary === 'left' ? rect.left - tooltipW - margin
           : rect.left + (rect.width / 2) - tooltipW / 2;
    } else if (primary === 'bottom') {
      top = rect.bottom + margin;
      left = secondary === 'right' ? rect.right + margin
           : secondary === 'left' ? rect.left - tooltipW - margin
           : rect.left + (rect.width / 2) - tooltipW / 2;
    } else if (primary === 'right') {
      left = rect.right + margin;
      top = secondary === 'top' ? rect.top - tooltipH + rect.height
          : secondary === 'bottom' ? rect.bottom
          : rect.top;
    } else if (primary === 'left') {
      left = rect.left - tooltipW - margin;
      top = secondary === 'top' ? rect.top - tooltipH + rect.height
          : secondary === 'bottom' ? rect.bottom
          : rect.top;
    }

    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    if (left < 20) left = 20;
    if (left + 400 > viewportWidth) left = viewportWidth - 420;
    if (top < 20) top = 20;
    if (top + 200 > viewportHeight) top = viewportHeight - 220;
    setModalPos({ top, left });
  };

  const navigateToStep = (nextStep) => {
    const stepData = TUTORIAL_STEPS[nextStep - 1];
    const currentRoute = location.pathname;
    const targetRoute = stepData.route;

    if (targetRoute && targetRoute !== currentRoute) {
      // Show transition overlay before navigating
      setTransitioning(true);
      setTransitionLabel(stepData.routeLabel || targetRoute);

      // Small delay so user sees the transition indicator
      setTimeout(() => {
        navigate(targetRoute);
        // Wait for target element to appear after navigation
        waitForTarget(stepData, () => {
          // Hold the transition a bit so it feels deliberate
          setTimeout(() => {
            setTransitioning(false);
            setStep(nextStep);
          }, 400);
        });
      }, 300);
    } else {
      setStep(nextStep);
    }
  };

  const handleNext = () => {
    if (step < TUTORIAL_STEPS.length) {
      navigateToStep(step + 1);
    } else {
      if (location.pathname !== '/') navigate('/');
      onClose();
    }
  };

  const handleBack = () => {
    if (step > 1) {
      navigateToStep(step - 1);
    } else {
      setStep(0);
    }
  };

  if (!open) return null;

  // Route transition overlay
  if (transitioning) {
    return (
      <>
        <div className={styles.tutorialOverlay} />
        <RouteTransition targetLabel={transitionLabel} visible />
      </>
    );
  }

  // Step 0: Welcome Screen
  if (step === 0) {
    return (
      <Modal isOpen={open} onOpenChange={onClose}>
        <Dialog className={styles.modalGlassBg} role="dialog" aria-modal="true" aria-label={t('beta.welcome.heading')}>
          <div className={styles.popupContent} style={{ textAlign: 'left', lineHeight: 1.6 }}>
            <Heading level={2} style={{ margin: '20px', fontWeight: 300, fontSize: '2rem', textAlign: 'center' }}>
              {t('beta.welcome.heading')}
            </Heading>
            <p><Trans i18nKey="beta.welcome.intro" components={{ b: <b /> }} /></p>
            <p><Trans i18nKey="beta.welcome.privacy" components={{ b: <b /> }} /></p>
            <p><Trans i18nKey="beta.welcome.feedback" components={{ b: <b /> }} /></p>
            <p>{t('beta.welcome.thanks')}</p>
            <div style={{ display: 'flex', gap: '15px', justifyContent: 'center', marginTop: 24 }}>
              <Button onPress={onClose} className={styles.secondaryBtn}
                style={{ alignSelf: 'center', border: 'none', textDecoration: 'none' }}>
                {t('tutorial.skip')}
              </Button>
              <Button className={styles.loginButton} onPress={() => navigateToStep(1)} autoFocus
                style={{ width: 'auto', paddingLeft: 30, paddingRight: 30 }}>
                {t('tutorial.startTour')}
              </Button>
            </div>
          </div>
        </Dialog>
      </Modal>
    );
  }

  // Tutorial Steps
  const currentStepData = TUTORIAL_STEPS[step - 1];
  const isLastStep = step === TUTORIAL_STEPS.length;

  return (
    <>
      <div className={styles.tutorialOverlay}>
        <SpotlightOverlay targetId={currentStepData.targetId} onPositionChange={handleSpotlightUpdate} />
      </div>

      <Dialog
        className={styles.tutorialBox}
        style={{
          top: modalPos ? modalPos.top : '50%',
          left: modalPos ? modalPos.left : '50%',
          transform: modalPos ? 'none' : 'translate(-50%, -50%)',
          position: 'fixed'
        }}
        role="dialog" aria-modal="true" aria-label={currentStepData.title}
      >
        <div className={styles.modalGlassBg}>
          <div className={`${styles.popupContent} ${styles.tutorialContent}`}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
              <Heading level={3} style={{ marginTop: 0 }}>{currentStepData.title}</Heading>
              <Button onPress={onClose} style={{ background: 'none', border: 'none', color: '#aaa', cursor: 'pointer', fontSize: '1.2rem', padding: 0 }}>x</Button>
            </div>
            <p style={{ lineHeight: 1.6, color: '#ddd' }}>{currentStepData.content}</p>
            <div className={styles.tutorialControls}>
              <div className={styles.dotsContainer}>
                {TUTORIAL_STEPS.map((_, i) => (
                  <div key={i} className={`${styles.dot} ${step - 1 === i ? styles.dotActive : ''}`} />
                ))}
              </div>
              <div className={styles.navButtons}>
                <Button className={styles.secondaryBtn} onPress={handleBack}>
                  {t('tutorial.back')}
                </Button>
                <Button className={styles.primaryBtn} onPress={handleNext}>
                  {isLastStep ? t('tutorial.finish') : t('tutorial.next')}
                </Button>
              </div>
            </div>
          </div>
        </div>
      </Dialog>
    </>
  );
}

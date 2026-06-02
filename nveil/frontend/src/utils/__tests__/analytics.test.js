// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  installConsentDefaults,
  updateConsent,
  trackEvent,
  trackPageView,
  trackSignup,
} from '../analytics'

beforeEach(() => {
  // Reset global state before each test
  window.dataLayer = []
  delete window.gtag
  // Clear cookies
  document.cookie = 'cookieConsent=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

describe('installConsentDefaults', () => {
  it('creates dataLayer if missing', () => {
    delete window.dataLayer
    installConsentDefaults()
    expect(Array.isArray(window.dataLayer)).toBe(true)
  })

  it('sets gtag function on window', () => {
    installConsentDefaults()
    expect(typeof window.gtag).toBe('function')
  })

  it('pushes consent default as first entry', () => {
    installConsentDefaults()
    // First gtag call should be consent default
    const consentEntry = window.dataLayer.find(
      (e) => e[0] === 'consent' && e[1] === 'default'
    )
    expect(consentEntry).toBeDefined()
    expect(consentEntry[2].analytics_storage).toBe('denied')
    expect(consentEntry[2].ad_storage).toBe('denied')
  })

  it('upgrades consent when cookieConsent=true', () => {
    document.cookie = 'cookieConsent=true'
    installConsentDefaults()
    const updateEntry = window.dataLayer.find(
      (e) => e[0] === 'consent' && e[1] === 'update'
    )
    expect(updateEntry).toBeDefined()
    expect(updateEntry[2].analytics_storage).toBe('granted')
  })

  it('does not upgrade when no cookie', () => {
    installConsentDefaults()
    const updateEntry = window.dataLayer.find(
      (e) => e[0] === 'consent' && e[1] === 'update'
    )
    expect(updateEntry).toBeUndefined()
  })
})

describe('updateConsent', () => {
  it('pushes granted consent update', () => {
    installConsentDefaults()
    updateConsent(true)
    const events = window.dataLayer.filter((e) => e.event === 'consent_update')
    expect(events).toHaveLength(1)
    expect(events[0].consent_granted).toBe(true)
  })

  it('pushes denied consent update', () => {
    installConsentDefaults()
    updateConsent(false)
    const events = window.dataLayer.filter((e) => e.event === 'consent_update')
    expect(events).toHaveLength(1)
    expect(events[0].consent_granted).toBe(false)
  })
})

describe('trackEvent', () => {
  it('pushes event to dataLayer', () => {
    trackEvent('button_click', { label: 'signup' })
    const entry = window.dataLayer.find((e) => e.event === 'button_click')
    expect(entry).toBeDefined()
    expect(entry.label).toBe('signup')
  })
})

describe('trackPageView', () => {
  it('pushes virtual_pageview with path', () => {
    trackPageView('/dashboard')
    const entry = window.dataLayer.find((e) => e.event === 'virtual_pageview')
    expect(entry).toBeDefined()
    expect(entry.page_path).toBe('/dashboard')
  })
})

describe('trackSignup', () => {
  it('pushes sign_up event with email', () => {
    trackSignup('user@example.com')
    const entry = window.dataLayer.find((e) => e.event === 'sign_up')
    expect(entry).toBeDefined()
    expect(entry.method).toBe('email')
    expect(entry.user_email).toBe('user@example.com')
  })
})

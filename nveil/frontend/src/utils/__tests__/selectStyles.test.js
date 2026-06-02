// SPDX-FileCopyrightText: 2026 NVEIL SAS
// SPDX-FileContributor: Pierre Jacquet
// SPDX-License-Identifier: AGPL-3.0-or-later

import { describe, it, expect } from 'vitest'
import { baseSelectStyles, darkSelectTheme, mergeSelectStyles } from '../selectStyles'

describe('selectStyles', () => {
  it('baseSelectStyles contains expected keys', () => {
    expect(baseSelectStyles).toHaveProperty('menu')
    expect(baseSelectStyles).toHaveProperty('option')
    expect(baseSelectStyles).toHaveProperty('singleValue')
  })

  it('darkSelectTheme overrides neutral0 color', () => {
    const theme = { colors: { neutral0: '#fff', primary: 'blue' } }
    const result = darkSelectTheme(theme)
    expect(result.colors.neutral0).toBe('#2f2e2e')
    expect(result.colors.primary).toBe('white')
  })

  it('mergeSelectStyles returns base styles when no overrides', () => {
    const styles = mergeSelectStyles()
    expect(styles.menu).toBe(baseSelectStyles.menu)
    expect(styles.option).toBe(baseSelectStyles.option)
  })

  it('mergeSelectStyles merges overrides on top of base', () => {
    const overrides = {
      menu: (base) => ({ ...base, zIndex: 999 }),
    }
    const styles = mergeSelectStyles(overrides)
    const result = styles.menu({}, {})
    expect(result).toHaveProperty('zIndex', 999)
    expect(result).toHaveProperty('backgroundColor', '#2f2e2e')
  })
})

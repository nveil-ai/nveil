# Styling Guide

CSS conventions, design tokens, and theming for the NVEIL frontend.

## Approach

**CSS Modules** for component-scoped styles. **Global CSS** (`index.css`) for design tokens and shared element styles. No preprocessors, no CSS-in-JS, no Tailwind.

## File conventions

| File | Purpose |
|------|---------|
| `ComponentName.module.css` | Scoped styles for `ComponentName.jsx` |
| `src/index.css` | Global styles, design tokens, React Aria overrides |
| `src/Chat/DeepChat.css` | Deep Chat component overrides |
| `src/Home/resizable-panels.css` | Panel layout overrides |

### Component example

```jsx
// MyComponent.jsx
import styles from "./MyComponent.module.css";

function MyComponent() {
  return <div className={styles.container}>...</div>;
}
```

```css
/* MyComponent.module.css */
.container {
  background: var(--bg-surface);
  border-radius: 12px;
  padding: 1rem;
}
```

## Design Tokens

The dark theme is the primary (and currently only) theme. Key values from `index.css`:

### Colors

| Token | Value | Usage |
|-------|-------|-------|
| Background (deep) | `#0a0a0f` | Page background |
| Background (surface) | `#1a1a2e` | Cards, panels |
| Background (elevated) | `#1e1e2e` | Modals, dropdowns |
| Accent | `#49fcb3` | Primary actions, links, highlights |
| Text primary | `#ffffff` | Headings, body text |
| Text secondary | `#a0a0b0` | Labels, captions |
| Border | `rgba(255, 255, 255, 0.08)` | Dividers, card borders |
| Error | `#ff4d6a` | Error states |

### Typography

| Property | Value |
|----------|-------|
| Font family | `InterTight`, system fallback |
| Font weight (body) | 400 |
| Font weight (heading) | 600 |
| Font size (body) | 14px |
| Font size (heading) | 18-24px |

### Spacing

Use multiples of `0.25rem` (4px grid):

| Size | Value | Usage |
|------|-------|-------|
| xs | `0.25rem` (4px) | Tight gaps |
| sm | `0.5rem` (8px) | Inner padding |
| md | `1rem` (16px) | Standard padding |
| lg | `1.5rem` (24px) | Section spacing |
| xl | `2rem` (32px) | Page margins |

### Borders & Radius

| Property | Value |
|----------|-------|
| Border radius (small) | `6px` |
| Border radius (medium) | `12px` |
| Border radius (large) | `16px` |
| Border radius (round) | `50%` |

## Glass morphism

Several components use a frosted glass effect:

```css
.glass {
  background: rgba(30, 30, 46, 0.7);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 12px;
}
```

Use this pattern for overlays, floating panels, and modal backdrops.

## React Aria styling

React Aria components are unstyled by default. Global overrides live in `index.css`:

```css
/* Example: Toast component */
[data-react-aria-toast] {
  background: var(--bg-elevated);
  border-radius: 8px;
  padding: 0.75rem 1rem;
  color: white;
}
```

When styling React Aria components, use the `data-*` attribute selectors provided by the library, not custom class names.

## Icons

Use **React Icons** exclusively:

```jsx
import { MdSettings } from "react-icons/md";
import { IoClose } from "react-icons/io5";
import { FaGithub } from "react-icons/fa";

<MdSettings size={20} />
```

Do not use inline SVGs, icon fonts, or other icon libraries.

## Do's and Don'ts

!!! success "Do"
    - Use CSS modules for all component styles
    - Follow the existing dark theme color palette
    - Use CSS custom properties for shared values
    - Use modern CSS features (nesting, `:has()`, container queries)
    - Match existing border radius, spacing, and glass morphism patterns

!!! failure "Don't"
    - Don't use inline styles (except for truly dynamic values like `width: ${pixels}px`)
    - Don't install CSS-in-JS libraries (styled-components, emotion, etc.)
    - Don't use Tailwind or utility-class frameworks
    - Don't create light theme variants (dark mode is the only theme)
    - Don't use `!important` — fix specificity instead
    - Don't hardcode colors — use the established palette values

# Components

Shared reusable components in `src/Components/` and feature-specific directories.

## Shared Components

| Component | Location | Description |
|-----------|----------|-------------|
| `Loading` | `Components/` | Full-page loading spinner |
| `ErrorBoundary` | `Components/` | React error boundary wrapper |
| `CookieBanner` | `Components/` | GDPR consent banner (GTM Consent Mode v2) |
| `ConfirmModal` | `Components/` | Generic confirmation dialog |
| `DataSourcesModal` | `Components/` | Data source picker for rooms |
| `VariablePickerModal` | `Components/` | Field/variable selector for viz configuration |
| `WelcomeModal` | `Components/` | First-time user onboarding |
| `UploadPanel` | `Data/` | File upload interface (drag-and-drop) |
| `SEO` | `Components/` | Meta tags via react-helmet-async |

## Visualization Controls

| Component | Location | Description |
|-----------|----------|-------------|
| `WidgetPanel` | `Viz/widgets/` | Container for all viz controls |
| `WidgetRenderer` | `Viz/widgets/` | Dispatches to correct control type |
| `SliderControl` | `Viz/widgets/` | Range input (React Aria Slider) |
| `SelectControl` | `Viz/widgets/` | Dropdown (React Select) |
| `SwitchControl` | `Viz/widgets/` | Toggle (React Aria Switch) |
| `TimelineControl` | `Viz/widgets/` | Timestep scrubber for animation |
| `SparklinePreview` | `Viz/widgets/` | Mini chart preview |
| `InfoPanel` | `Viz/widgets/` | Metadata display panel |
| `ExportDialog` | `Viz/widgets/` | Export viz to image/HTML |

## Palette Components

| Component | Location | Description |
|-----------|----------|-------------|
| `PaletteGallery` | `Explore/` | Color palette showcase |
| `PaletteGenerator` | `Explore/` | Custom palette creation |
| `PaletteMenu` | `Viz/` | In-viz palette switcher |

## UI Library

All interactive components should use **React Aria** (`react-aria-components`):

- Button, Checkbox, Dialog, ModalOverlay
- Slider, Switch, Select, ComboBox
- Tooltip, Toast, Disclosure

Icons come from **React Icons** (`react-icons`):

- Material Design: `Md*` prefix
- Ionicons: `Io*` prefix
- Font Awesome: `Fa*` prefix

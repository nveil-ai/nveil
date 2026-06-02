# NVEIL Frontend

**React application for the NVEIL visualization platform**

The frontend is a single-page application built with React 18, Vite, and CSS Modules. It provides real-time chat with an AI assistant, interactive visualization rendering (Plotly, VTK.js, DeckGL), dashboard management, and file uploads.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Framework** | React 18.3 |
| **Router** | React Router 7.7 |
| **State** | React Context API |
| **Styling** | CSS Modules + global CSS |
| **UI Components** | React Aria, React Select, React Icons |
| **Visualization** | Trame (VTK.js), DeckGL, Plotly |
| **Chat** | Deep Chat React |
| **i18n** | i18next (English, French) |
| **Build** | Vite (Rolldown) |
| **Testing** | Vitest + Testing Library |
| **Linting** | ESLint 9 |

---

## Project Structure

```
src/
├── App.jsx                 # Router + context providers
├── main.jsx                # Entry point
├── index.css               # Global styles + design tokens
├── i18n.js                 # Internationalization setup
│
├── Auth/                   # Login, signup, OAuth, password reset
├── Chat/                   # AI chat (Deep Chat), WebSocket context
├── Home/                   # Main layout (resizable panels)
├── Viz/                    # Visualization (Trame iframe + widgets)
├── Dashboard/              # Dashboard list + grid view
├── Data/                   # File upload + data source manager
├── Room/                   # Room context (workspace lifecycle)
├── Explore/                # Example gallery
├── Settings/               # User preferences
├── Plan/                   # Pricing page
├── Feedback/               # Feedback form
├── NavBar/                 # Navigation bar
├── Components/             # Shared components (modals, banners)
├── hooks/                  # Custom React hooks
├── utils/                  # Helpers (analytics, routing)
├── Locales/                # Translation files (en, fr)
├── Fonts/                  # InterTight variable font
└── assets/                 # Static images/icons
```

---

## Quick Links

- [Architecture](architecture/) — Routing, state, API layer, i18n
- [Pages](pages/) — Per-page documentation
- [Components](components/) — Shared UI components
- [Developer Guide](developer/) — Practices, styling, testing

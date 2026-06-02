# Separation of Concerns

Clear boundaries between frontend and backend responsibilities.

## Core principle

**UI logic belongs in the frontend. Data logic belongs in the backend.**

The frontend (React) owns all user interaction, layout, styling, and visual state. The backend (Python/FastAPI) owns data processing, persistence, authentication, and business rules. The Trame viz service is a rendering engine, not a UI framework.

## What belongs WHERE

### Frontend (React)

- Page layout and navigation
- Form validation and user feedback
- Component state (open/closed, selected, loading)
- Visual effects (animations, transitions, hover states)
- Widget rendering (sliders, selects, toggles)
- Theme switching and styling
- Internationalization (i18n)
- Analytics and consent management
- Drag-and-drop interactions
- Keyboard shortcuts and accessibility

### Backend (Python)

- Authentication and authorization
- Database CRUD operations
- File processing and storage
- LLM/AI workflow orchestration
- ASP constraint solving
- Data transformation (Choregraph)
- Visualization spec generation
- WebSocket event broadcasting

### Viz Service (Trame)

- Rendering visualizations (Plotly, VTK, DeckGL)
- Data loading from workspace files
- Frame construction from VisuSpec
- Timestep switching

!!! warning "Avoid building UI in Trame"
    Do not use Trame/Vuetify for UI components (modals, forms, controls). The frontend React app handles all user-facing UI. Trame only renders the visualization canvas.

## Anti-patterns to avoid

### Don't duplicate state

Bad: Backend stores UI preferences that only the frontend needs.

Good: Use `localStorage` or React state for UI-only preferences.

### Don't proxy simple reads

Bad: Frontend calls server, server calls file service, file service reads a config file, returns to server, returns to frontend.

Good: If the frontend can read from an existing API response, use that data directly.

### Don't build widgets in Python

Bad: Viz service generates HTML for control widgets.

Good: Viz service sends widget metadata (type, min, max, options), frontend renders the actual control using React Aria components.

### Don't mix styling systems

Bad: Inline styles, styled-components, Tailwind, and CSS modules in the same component.

Good: CSS modules for component styles, `index.css` for global tokens. Nothing else.

## Data flow patterns

### Chat message

```
User types message
  → Frontend validates input
  → POST /ai/sendUserMessage
  → AI service runs LangGraph workflow
  → AI service generates viz spec
  → Server broadcasts via WebSocket
  → Frontend updates chat + triggers viz reload
```

### File upload

```
User drops file
  → Frontend shows upload progress
  → POST /server/data/upload (multipart)
  → Server proxies to File service
  → File service stores + creates DB record
  → Frontend updates file list
  → User clicks "Link to Room"
  → POST /server/rooms/{id}/link-files
  → File service creates symlinks
  → Frontend triggers viz reload
```

### Widget interaction

```
User moves slider
  → Frontend updates local state immediately (responsiveness)
  → Frontend sends command via /viz/send
  → Viz container updates rendering
  → Trame streams updated frame via WebSocket
  → Frontend displays new frame
```

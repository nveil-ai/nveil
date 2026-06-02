# Home & Chat

The main application page combining AI chat and visualization in resizable panels.

## Layout

```
┌──────────────────────────────────────────┐
│                 NavBar                    │
├────────────┬─────────────────────────────┤
│            │                             │
│   Chat     │      Visualization          │
│  (left)    │        (right)              │
│            │                             │
│            ├─────────────────────────────┤
│            │    Widget Controls          │
├────────────┴─────────────────────────────┤
```

- **Resizable panels**: `react-resizable-panels` allows dragging the divider
- **Floating chat**: Chat can be undocked into a draggable floating window (`useFloatingWindow` hook)
- **Landing page**: Unauthenticated users see the SEO landing page instead

## Chat

`Chat/Chat.jsx` — AI chat powered by Deep Chat React.

### Features

- Real-time message streaming via WebSocket
- Custom input (`CustomInput.jsx`) with `@` mention suggestions
- File upload integration
- Message history loaded from `/server/get_history`
- Messages sent via `POST /ai/sendUserMessage`

### Deep Chat customization

The Deep Chat component is heavily styled via `Chat/DeepChat.css` to match the dark theme. Configuration is passed as props (no external config file).

## Floating window

`Home/useFloatingWindow.js` — Custom hook for dock/undock behavior.

- **Drag**: Click and drag the title bar
- **Resize**: Drag corners/edges
- **Minimize**: Collapse to icon
- **Dock/Undock**: Toggle between panel and floating modes
- **Persistence**: Docked state saved to `localStorage` (`nveil_chatDocked`)

# Architecture

The frontend is organized by feature (one directory per page/domain), with shared state managed through React Context providers.

```mermaid
graph TB
    subgraph Providers
        Auth["AuthContext"]
        WS["WebSocketContext"]
        Room["RoomContext"]
    end

    subgraph Pages
        Home["Home"]
        Dash["Dashboard"]
        Data["Data Manager"]
        Settings["Settings"]
    end

    subgraph Core
        Chat["Chat (Deep Chat)"]
        Viz["Viz (Trame)"]
        Widgets["Widget Panel"]
        Kedro["Kedro Viz (pipeline DAG)"]
    end

    Auth --> WS --> Room
    Room --> Home
    Home --> Chat
    Home --> Viz
    Viz --> Widgets
    Viz --> Kedro
    Room --> Dash
    Room --> Data
```

- [Routing](routing.md) — Routes, lazy loading, code splitting
- [State Management](state.md) — Context providers (Auth, Room, WebSocket)
- [API Layer](api.md) — Backend communication, CSRF, token refresh
- [Internationalization](i18n.md) — i18next setup, translations

# Routing

React Router 7.7 with lazy-loaded pages and Suspense boundaries.

## Routes

| Path | Component | Lazy | Description |
|------|-----------|------|-------------|
| `/` | Home / Landing | No | Main app or landing page (auth-dependent) |
| `/room/:roomToken` | Home | No | Room with specific token |
| `/settings` | Settings | Yes | User preferences |
| `/explore` | Explore | Yes | Example gallery |
| `/feedback` | Feedback | Yes | Feedback form |
| `/plan` | Plan | Yes | Pricing page |
| `/data` | DataManager | Yes | File upload and management |
| `/dashboards` | DashboardList | Yes | Dashboard gallery |
| `/dashboard/:dashboardToken` | DashboardView | Yes | Dashboard viewer |
| `/success` | CheckoutSuccess | Yes | Payment success |
| `/cancel`, `/error` | CheckoutError | Yes | Payment error |
| `*` | NotFound | No | 404 page |

## Provider hierarchy

All routes are wrapped in nested context providers:

```jsx
<AuthProvider>
  <WebSocketProvider>
    <RoomProvider>
      <Routes>...</Routes>
    </RoomProvider>
  </WebSocketProvider>
</AuthProvider>
```

## Code splitting

Heavy visualization libraries are isolated in vendor chunks via `vite.config.js`:

| Chunk | Libraries | Size |
|-------|-----------|------|
| `vendor-plotly` | plotly.js | ~4.6 MB |
| `vendor-deckgl` | deck.gl, maplibre-gl, d3 | ~1.8 MB |
| `vendor-forcegraph` | d3, force-graph | ~300 KB |
| `vendor-react` | react, react-dom, react-router | ~200 KB |

These are only loaded when the corresponding page/component is rendered.

## SEO

- `react-helmet-async` for dynamic meta tags per page
- Puppeteer-based prerendering for the landing page (`prerender.js`)
- Sitemap plugin generates `/explore`, `/feedback`, `/plan` routes
- `robots.txt` disallows `/viz/`, `/server/`, `/cdn-cgi/`

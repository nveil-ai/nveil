# Adding Pages

How to add a new route and page component to the frontend.

## Step 1: Create the component

Create a new directory under `src/`:

```
src/
└── MyPage/
    ├── MyPage.jsx
    └── MyPage.module.css
```

```jsx
// MyPage.jsx
import styles from "./MyPage.module.css";

function MyPage() {
  return (
    <div className={styles.container}>
      <h1>My Page</h1>
    </div>
  );
}

export default MyPage;
```

## Step 2: Add the route

In `src/App.jsx`, add a lazy import and route:

```jsx
const MyPage = lazy(() => import("./MyPage/MyPage"));

// Inside <Routes>
<Route
  path="/my-page"
  element={
    <Suspense fallback={<Loading />}>
      <MyPage />
    </Suspense>
  }
/>
```

## Step 3: Add navigation

Add a link in `NavBar/NavBar.jsx`:

```jsx
<NavLink to="/my-page">{t("nav.myPage")}</NavLink>
```

## Step 4: Add translations

Add keys to both `src/Locales/en/common.json` and `src/Locales/fr/common.json`:

```json
{
  "nav": {
    "myPage": "My Page"
  },
  "myPage": {
    "title": "My Page Title"
  }
}
```

## Step 5: Add SEO meta tags

Use the `SEO` component at the top of your page:

```jsx
import SEO from "../Components/SEO";

function MyPage() {
  return (
    <>
      <SEO title="My Page" description="Description for search engines" />
      <div>...</div>
    </>
  );
}
```

## Checklist

- [ ] Component created with CSS module
- [ ] Route added in `App.jsx` (lazy-loaded)
- [ ] NavBar link added (if applicable)
- [ ] Translations added (en + fr)
- [ ] SEO meta tags added
- [ ] Tested at the route URL

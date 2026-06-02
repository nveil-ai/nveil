# Testing

Vitest + Testing Library for unit and component tests.

## Setup

| Tool | Version | Purpose |
|------|---------|---------|
| Vitest | 4.1.2 | Test runner |
| @testing-library/react | 16.3.2 | Component rendering |
| @testing-library/user-event | 14.6.1 | User interaction simulation |
| @testing-library/jest-dom | 6.9.1 | DOM matchers |

Configuration: `vitest.config.js` (jsdom environment, v8 coverage provider).

## Running tests

```bash
# Watch mode
npm run test

# Single run
npm run test:run

# With coverage
npm run test:coverage
```

## Writing tests

### File location

Tests go in `__tests__/` directories next to the code they test:

```
src/
└── utils/
    ├── analytics.js
    └── __tests__/
        └── analytics.test.js
```

### Example

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import MyComponent from "../MyComponent";

describe("MyComponent", () => {
  it("renders the title", () => {
    render(<MyComponent />);
    expect(screen.getByText("My Title")).toBeInTheDocument();
  });

  it("handles click", async () => {
    const user = userEvent.setup();
    render(<MyComponent />);
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Clicked")).toBeInTheDocument();
  });
});
```

### Testing with context

Components that use `useAuth()`, `useRoom()`, or `useWebSocket()` need their providers:

```jsx
import { AuthProvider } from "../../Auth/AuthContext";

function renderWithAuth(component) {
  return render(
    <AuthProvider>{component}</AuthProvider>
  );
}
```

## Coverage

Coverage reports are generated in `lcov` and `text` formats. The coverage target is the entire `src/` directory.

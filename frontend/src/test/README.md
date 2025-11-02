# Frontend Testing

This project uses **Vitest** as the test runner with **@testing-library/svelte** for component testing.

## Running Tests

```bash
# Run tests once
npm run test

# Watch mode (re-run on changes)
npm run test:watch

# Interactive UI
npm run test:ui

# Coverage report
npm run test:coverage
```

## Test Structure

Tests are colocated with source files using the `.test.ts` pattern:

```
src/
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   └── client.test.ts  # ← Tests here
│   ├── Counter.svelte
│   └── Counter.test.ts      # ← Tests here
└── test/
    └── setup.ts             # ← Global test setup
```

## Configuration

- **Test Runner**: Vitest (`vitest.config.ts`)
- **Environment**: happy-dom (lightweight DOM for testing)
- **Global Setup**: `src/test/setup.ts`

## Writing Tests

### Basic Unit Tests

```typescript
import { describe, it, expect } from 'vitest'

describe('MyFunction', () => {
    it('does something', () => {
        expect(myFunction(1, 2)).toBe(3)
    })
})
```

### Component Tests (Svelte 5)

```typescript
import { render, screen } from '@testing-library/svelte'
import { describe, it, expect } from 'vitest'
import MyComponent from './MyComponent.svelte'

describe('MyComponent', () => {
    it('renders correctly', () => {
        render(MyComponent)
        expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('handles user interactions', async () => {
        render(MyComponent)
        const button = screen.getByRole('button')
        await button.click()
        // Add assertions
    })
})
```

## CI Integration

Tests automatically run in CI on every PR via the `frontend-ci.yml` workflow.

# frontend testing

this project uses **Vitest** as the test runner with **@testing-library/svelte** for component testing.

## running tests

```bash
# run tests once
npm run test

# watch mode (re-run on changes)
npm run test:watch

# interactive UI
npm run test:ui

# coverage report
npm run test:coverage
```

## test structure

tests are colocated with source files using the `.test.ts` pattern:

```
src/
├── lib/
│   ├── api/
│   │   ├── client.ts
│   │   └── client.test.ts  # ← tests here
│   ├── Counter.svelte
│   └── Counter.test.ts      # ← tests here
└── test/
    └── setup.ts             # ← global test setup
```

## configuration

- **test runner**: Vitest (`vitest.config.ts`)
- **environment**: happy-dom (lightweight DOM for testing)
- **global setup**: `src/test/setup.ts`

## writing tests

### basic unit tests

```typescript
import { describe, it, expect } from 'vitest'

describe('MyFunction', () => {
	it('does something', () => {
		expect(myFunction(1, 2)).toBe(3)
	})
})
```

### component tests (Svelte 5)

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
		// add assertions
	})
})
```

## CI integration

tests automatically run in CI on every PR via the `frontend-ci.yml` workflow.

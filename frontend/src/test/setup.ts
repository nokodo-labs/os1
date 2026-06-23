import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/svelte'
import { afterEach } from 'vitest'

if (!Element.prototype.animate) {
	Object.defineProperty(Element.prototype, 'animate', {
		configurable: true,
		value() {
			return {
				cancel() {},
				finished: Promise.resolve(),
			}
		},
	})
}

// cleanup after each test
afterEach(() => {
	cleanup()
})

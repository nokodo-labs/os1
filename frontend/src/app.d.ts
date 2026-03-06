// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
	namespace App {
		// interface Error {}
		// interface Locals {}
		// interface PageData {}
		interface PageState {
			next?: string
			email?: string
		}
		// interface Platform {}
	}

	// splash screen bridge (set by inline script in app.html)
	interface Window {
		__nokodoSplash?: { shimmerStarted: Promise<void> }
	}
}

export {}

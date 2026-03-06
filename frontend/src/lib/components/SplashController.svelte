<script lang="ts">
	import { appReadiness } from '$lib/stores/appReadiness.svelte'
	import { onMount } from 'svelte'

	function isReducedMotion() {
		return window.matchMedia('(prefers-reduced-motion: reduce)').matches
	}

	function wait(ms: number) {
		return new Promise<void>((resolve) => setTimeout(resolve, ms))
	}

	onMount(() => {
		const splashScreen = document.getElementById('nokodo-splash-screen')
		const brand = document.getElementById('nokodo-splash-brand')
		if (!splashScreen || !brand) {
			console.warn('splash elements not found; skipping animation')
			return
		}

		const fadeOutMs = isReducedMotion() ? 150 : 300

		let cancelled = false

		const start = async () => {
			try {
				// expand/shimmer is driven pre-hydration (app.html). Even if the app
				// becomes ready quickly, we only fade once shimmer has started.
				const shimmerStarted: Promise<void> =
					(window as unknown as { __nokodoSplash?: { shimmerStarted?: Promise<void> } })
						.__nokodoSplash?.shimmerStarted ?? Promise.resolve()

				await Promise.all([shimmerStarted, appReadiness.waitForReady()])
				if (cancelled) return

				splashScreen.style.transition = `opacity ${fadeOutMs}ms ease-out`
				splashScreen.style.opacity = '0'
				await wait(fadeOutMs)
				if (cancelled) return

				splashScreen.remove()
			} catch (error) {
				console.error('splash animation error:', error)
				splashScreen.remove()
			}
		}

		void start()

		return () => {
			cancelled = true
		}
	})
</script>

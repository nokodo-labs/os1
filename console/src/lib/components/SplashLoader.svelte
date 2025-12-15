<script lang="ts">
	import { onMount } from 'svelte'
	import NokodoLoader from './NokodoLoader.svelte'

	let { ready = false } = $props()

	let container = $state<HTMLElement>()
	let splashScreen = $state<HTMLElement>()
	let isVisible = $state(true)

	// Loader state
	let expanded = $state(false)
	let shimmer = $state(false)

	onMount(() => {
		// Theme logic from the original script
		const metaThemeColorTag = document.querySelector('meta[name="theme-color"]')
		const prefersDarkTheme = window.matchMedia('(prefers-color-scheme: dark)').matches

		if (!localStorage?.theme) {
			localStorage.theme = 'system'
		}

		if (localStorage.theme === 'system') {
			document.documentElement.classList.add(prefersDarkTheme ? 'dark' : 'light')
			if (metaThemeColorTag)
				metaThemeColorTag.setAttribute('content', prefersDarkTheme ? '#171717' : '#ffffff')
		} else if (localStorage.theme === 'oled-dark') {
			document.documentElement.style.setProperty('--color-gray-800', '#101010')
			document.documentElement.style.setProperty('--color-gray-850', '#050505')
			document.documentElement.style.setProperty('--color-gray-900', '#000000')
			document.documentElement.style.setProperty('--color-gray-950', '#000000')
			document.documentElement.classList.add('dark')
			if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#000000')
		} else if (localStorage.theme === 'light') {
			document.documentElement.classList.add('light')
			if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#ffffff')
		} else if (localStorage.theme === 'her') {
			document.documentElement.classList.add('her')
			if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#983724')
		} else {
			document.documentElement.classList.add('dark')
			if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#171717')
		}

		window.matchMedia('(prefers-color-scheme: dark)').addListener((e) => {
			if (localStorage.theme === 'system') {
				if (e.matches) {
					document.documentElement.classList.add('dark')
					document.documentElement.classList.remove('light')
					if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#171717')
				} else {
					document.documentElement.classList.add('light')
					document.documentElement.classList.remove('dark')
					if (metaThemeColorTag) metaThemeColorTag.setAttribute('content', '#ffffff')
				}
			}
		})

		initNokodoSplash()
	})

	function initNokodoSplash() {
		if (document.documentElement.classList.contains('her')) return
		const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
		const timing = {
			okHold: 500,
			expansion: 800,
			pause: 200,
			fadeOut: 300,
		}
		if (prefersReducedMotion) {
			timing.okHold = 100
			timing.expansion = 300
			timing.pause = 50
		}

		if (container) {
			container.style.display = 'block'
		}
		setTimeout(() => {
			startSplashSequence(timing)
		}, timing.okHold)
	}

	async function startSplashSequence(timing: any) {
		try {
			await expandBrand(timing.expansion)
			await new Promise((resolve) => setTimeout(resolve, 200))

			shimmer = true

			// Wait for ready prop to be true
			if (!ready) {
				await waitForAppReady()
			}

			shimmer = false
			await fadeOutSplash(timing.fadeOut)
		} catch (error) {
			console.error('Splash animation error:', error)
			// Fallback: immediately remove splash
			isVisible = false
		}
	}

	function waitForAppReady() {
		return new Promise<void>((resolve) => {
			const checkInterval = setInterval(() => {
				if (ready) {
					clearInterval(checkInterval)
					resolve()
				}
			}, 100)
		})
	}

	function expandBrand(duration: number) {
		return new Promise<void>((resolve) => {
			expanded = true
			setTimeout(resolve, duration)
		})
	}

	function fadeOutSplash(duration: number) {
		return new Promise<void>((resolve) => {
			if (document.documentElement.classList.contains('her')) {
				return
			}

			if (splashScreen) {
				splashScreen.style.transition = `opacity ${duration}ms ease-out`
				splashScreen.style.opacity = '0'

				setTimeout(() => {
					isVisible = false
					resolve()
				}, duration)
			} else {
				resolve()
			}
		})
	}
</script>

{#if isVisible}
	<div
		bind:this={splashScreen}
		id="splash-screen"
		style="position: fixed; z-index: 9999; top: 0; left: 0; width: 100%; height: 100%"
	>
		<div
			style="
				position: absolute;
				top: 33%;
				left: 50%;

				width: 24rem;
				transform: translateX(-50%);

				display: flex;
				flex-direction: column;
				align-items: center;
			"
		>
			<img
				id="logo-her"
				style="width: auto; height: 13rem"
				src="/static/splash.png"
				class="animate-pulse-fast"
				alt="splash"
			/>

			<div style="position: relative; width: 24rem; margin-top: 0.5rem">
				<div
					id="progress-background"
					style="
						position: absolute;
						width: 100%;
						height: 0.75rem;

						border-radius: 9999px;
						background-color: #fafafa9a;
					"
				></div>

				<div
					id="progress-bar"
					style="
						position: absolute;
						width: 0%;
						height: 0.75rem;
						border-radius: 9999px;
						background-color: #fff;
					"
					class="bg-white"
				></div>
			</div>
		</div>

		<div
			bind:this={container}
			id="splash-container"
			style="
				position: absolute;
				top: 50%;
				left: 50%;
				transform: translate(-50%, -50%);
				text-align: center;
				display: none;
			"
		>
			<NokodoLoader {expanded} {shimmer} />
		</div>
	</div>
{/if}

<style>
	/* Copied styles */
	/* :global(html) {
		overflow-y: hidden !important;
		overscroll-behavior-y: none;
	} */

	#splash-screen {
		background: #fff;
	}

	:global(html.dark) #splash-screen {
		background: #000;
	}

	:global(html.her) #splash-screen {
		background: #983724;
	}

	#logo-her,
	#progress-background,
	#progress-bar {
		display: none;
	}

	:global(html.her) #logo-her,
	:global(html.her) #progress-background,
	:global(html.her) #progress-bar {
		display: initial;
	}

	:global(html.her) #splash-container {
		display: none !important;
	}

	:global(html.her) #logo-her {
		display: block;
		filter: invert(1);
	}

	:global(html.her) #progress-background {
		display: block;
	}

	:global(html.her) #progress-bar {
		display: block;
	}

	@media (max-width: 24rem) {
		:global(html.her) #progress-background {
			display: none;
		}

		:global(html.her) #progress-bar {
			display: none;
		}
	}

	@keyframes pulse {
		50% {
			opacity: 0.65;
		}
	}

	.animate-pulse-fast {
		animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
	}
</style>

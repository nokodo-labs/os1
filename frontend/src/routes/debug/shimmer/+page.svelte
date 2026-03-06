<script lang="ts">
	import { browser, dev } from '$app/environment'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
	import { onDestroy } from 'svelte'

	type PreviewBackground = 'glass' | 'dark' | 'light'

	let shimmer = $state(true)
	let expanded = $state(true)
	let opacity = $state(0.85)
	let fontSizeRem = $state(3.25)
	let shimmerSeconds = $state(1.8)
	let background = $state<PreviewBackground>('glass')

	let isDark = $state<boolean>(false)
	let previousDarkClass: boolean | null = null

	$effect(() => {
		if (!dev) return
		const root = document.documentElement
		if (previousDarkClass === null) {
			previousDarkClass = root.classList.contains('dark')
			isDark = previousDarkClass
		}

		root.classList.toggle('dark', isDark)
	})

	onDestroy(() => {
		const root = document.documentElement
		if (previousDarkClass === null) return
		root.classList.toggle('dark', previousDarkClass)
	})

	let splashIframe = $state<HTMLIFrameElement | null>(null)
	let splashPreviewSrc = $state('/splash-preview.html')
	$effect(() => {
		if (!browser) return
		splashPreviewSrc = new URL('/splash-preview.html', window.location.origin).toString()
	})

	function openSplashPreviewStandalone() {
		if (!browser) return
		window.open(splashPreviewSrc, '_blank', 'noopener,noreferrer')
	}

	function reloadSplashPreview() {
		const iframe = splashIframe
		if (!iframe) return
		iframe.src = iframe.src
	}

	const loaderVars = $derived.by(() => {
		const safeOpacity = Math.min(1, Math.max(0, opacity))
		const safeFont = Math.max(1.5, Math.min(6, fontSizeRem))
		const safeSeconds = Math.max(0.2, Math.min(12, shimmerSeconds))

		return [
			`--nokodo-loader-font-size: ${safeFont}rem`,
			`--shimmer-duration: ${safeSeconds}s`,
			`opacity: ${safeOpacity}`,
		].join('; ')
	})

	const backgroundClass = $derived.by(() => {
		switch (background) {
			case 'dark':
				return 'bg-black'
			case 'light':
				return 'bg-white'
			default:
				return 'bg-[radial-gradient(80%_80%_at_50%_20%,rgba(255,255,255,0.08),transparent_60%),radial-gradient(70%_70%_at_20%_70%,rgba(120,120,255,0.08),transparent_55%),radial-gradient(70%_70%_at_80%_80%,rgba(0,255,255,0.06),transparent_55%),linear-gradient(180deg,rgba(10,10,10,0.95),rgba(10,10,10,0.95))]'
		}
	})
</script>

<div class="mx-auto w-full max-w-6xl px-6 pt-10 pb-24">
	<div class="flex flex-col gap-2">
		<h1 class="text-xl font-semibold">animation playground</h1>
		<p class="text-muted-foreground text-sm">
			dev-only page to preview the splash screen shimmer and the nokodo loader.
		</p>
		<div class="text-muted-foreground flex items-center gap-2 text-sm">
			<span>splash:</span>
			<button class="underline" type="button" onclick={openSplashPreviewStandalone}>
				open standalone preview
			</button>
		</div>
	</div>

	<div class="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
		<section class="rounded-2xl border border-foreground/10 bg-black/20 p-5">
			<div class="flex items-center justify-between gap-3">
				<h2 class="text-base font-semibold">splash preview</h2>
				<div class="flex items-center gap-2">
					<button
						class="rounded-xl border border-foreground/10 bg-black/30 px-3 py-2 text-sm hover:bg-black/40"
						onclick={reloadSplashPreview}
						type="button"
					>
						reload
					</button>
				</div>
			</div>

			<div class="mt-4 overflow-hidden rounded-2xl border border-foreground/10 bg-black/30">
				<iframe
					src={splashPreviewSrc}
					class="h-[780px] w-full"
					bind:this={splashIframe}
					title="splash preview"
				></iframe>
			</div>
		</section>

		<section class="rounded-2xl border border-foreground/10 bg-black/20 p-5">
			<div class="flex items-center justify-between gap-3">
				<h2 class="text-base font-semibold">nokodo loader</h2>
				<div class="flex items-center gap-3">
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" bind:checked={isDark} />
						dark
					</label>
				</div>
			</div>

			<div class="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">shimmer</span>
					<input type="checkbox" bind:checked={shimmer} />
				</label>
				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">expanded</span>
					<input type="checkbox" bind:checked={expanded} />
				</label>

				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">opacity</span>
					<input type="range" min="0" max="1" step="0.01" bind:value={opacity} />
				</label>
				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">shimmer (s)</span>
					<input type="range" min="0.2" max="12" step="0.2" bind:value={shimmerSeconds} />
				</label>

				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">size (rem)</span>
					<input type="range" min="1.5" max="6" step="0.05" bind:value={fontSizeRem} />
				</label>

				<label class="flex items-center justify-between gap-3 text-sm">
					<span class="text-muted-foreground">background</span>
					<select
						class="rounded-xl border border-foreground/10 bg-black/30 px-3 py-2 text-sm"
						bind:value={background}
					>
						<option value="glass">glass</option>
						<option value="dark">dark</option>
						<option value="light">light</option>
					</select>
				</label>
			</div>

			<div class="mt-5 overflow-hidden rounded-2xl border border-foreground/10">
				<div class="grid min-h-[780px] place-items-center p-10 {backgroundClass}">
					<div style={loaderVars}>
						<NokodoLoader {shimmer} {expanded} className="opacity-100" />
					</div>
				</div>
			</div>
		</section>
	</div>
</div>

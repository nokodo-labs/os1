<script lang="ts">
	/**
	 * dev instrumentation for the android keyboard/viewport problem (F101): a live
	 * dump of every number the composer's bottom anchor is computed from. gated by
	 * the `vvdebug` query param at the call site, never a product surface.
	 */

	import { tick } from 'svelte'

	interface Props {
		/** the page shell whose bottom edge the composer hangs off. */
		shell: HTMLElement | null
		/** the composer overlay itself. */
		overlay: HTMLElement | null
		/** the lift the page currently applies to that edge. */
		overhang: number
	}

	const { shell, overlay, overhang }: Props = $props()

	interface Metrics {
		innerHeight: number
		scrollY: number
		vvHeight: number
		vvOffsetTop: number
		vvPageTop: number
		vvScale: number
		appHeight: string
		shellTop: number
		shellBottom: number
		overlayTop: number
		overlayBottom: number
	}

	const EMPTY: Metrics = {
		innerHeight: 0,
		scrollY: 0,
		vvHeight: 0,
		vvOffsetTop: 0,
		vvPageTop: 0,
		vvScale: 0,
		appHeight: '',
		shellTop: 0,
		shellBottom: 0,
		overlayTop: 0,
		overlayBottom: 0,
	}

	let metrics = $state<Metrics>(EMPTY)
	let eventCount = $state(0)
	let lastEvent = $state('mount')
	let status = $state('tap to copy')
	let blobEl = $state<HTMLTextAreaElement | null>(null)
	let showBlob = $state(false)

	/** the visible bottom in client space: client rects share the layout viewport origin. */
	const visibleBottom = $derived(metrics.vvOffsetTop + metrics.vvHeight)
	/** unclamped, so a negative value (shell already above the fold) stays readable. */
	const shellDelta = $derived(metrics.shellBottom - visibleBottom)
	const overlayDelta = $derived(metrics.overlayBottom - visibleBottom)

	function read(source: string) {
		const vv = window.visualViewport
		const shellRect = shell?.getBoundingClientRect() ?? null
		const overlayRect = overlay?.getBoundingClientRect() ?? null
		metrics = {
			innerHeight: window.innerHeight,
			scrollY: window.scrollY,
			vvHeight: vv?.height ?? 0,
			vvOffsetTop: vv?.offsetTop ?? 0,
			vvPageTop: vv?.pageTop ?? 0,
			vvScale: vv?.scale ?? 0,
			appHeight:
				getComputedStyle(document.documentElement)
					.getPropertyValue('--app-height')
					.trim() || 'unset',
			shellTop: shellRect?.top ?? 0,
			shellBottom: shellRect?.bottom ?? 0,
			overlayTop: overlayRect?.top ?? 0,
			overlayBottom: overlayRect?.bottom ?? 0,
		}
		eventCount += 1
		lastEvent = source
	}

	$effect(() => {
		// re-read whenever the page publishes a new lift
		void overhang
		read('overhang')
	})

	$effect(() => {
		let settleTimer: ReturnType<typeof setTimeout> | null = null
		const track = (source: string) => () => {
			read(source)
			// same trailing pass the page measures with: the keyboard animation keeps
			// firing events and the last one is not always the settled state.
			if (settleTimer !== null) clearTimeout(settleTimer)
			settleTimer = setTimeout(() => {
				settleTimer = null
				read(`${source} settled`)
			}, 300)
		}

		const onWindowResize = track('window resize')
		const onWindowScroll = track('window scroll')
		const onViewportResize = track('vv resize')
		const onViewportScroll = track('vv scroll')

		read('mount')
		window.addEventListener('resize', onWindowResize, { passive: true })
		window.addEventListener('scroll', onWindowScroll, { passive: true })
		window.visualViewport?.addEventListener('resize', onViewportResize, { passive: true })
		window.visualViewport?.addEventListener('scroll', onViewportScroll, { passive: true })

		return () => {
			if (settleTimer !== null) clearTimeout(settleTimer)
			window.removeEventListener('resize', onWindowResize)
			window.removeEventListener('scroll', onWindowScroll)
			window.visualViewport?.removeEventListener('resize', onViewportResize)
			window.visualViewport?.removeEventListener('scroll', onViewportScroll)
		}
	})

	function px(value: number): string {
		return value.toFixed(1)
	}

	const blob = $derived(
		[
			`event #${eventCount} (${lastEvent})`,
			`innerHeight ${px(metrics.innerHeight)}`,
			`scrollY ${px(metrics.scrollY)}`,
			`vv.height ${px(metrics.vvHeight)}`,
			`vv.offsetTop ${px(metrics.vvOffsetTop)}`,
			`vv.pageTop ${px(metrics.vvPageTop)}`,
			`vv.scale ${metrics.vvScale}`,
			`--app-height ${metrics.appHeight}`,
			`shell top/bottom ${px(metrics.shellTop)} / ${px(metrics.shellBottom)}`,
			`overlay top/bottom ${px(metrics.overlayTop)} / ${px(metrics.overlayBottom)}`,
			`visible bottom ${px(visibleBottom)}`,
			`shell delta ${px(shellDelta)}`,
			`overlay delta ${px(overlayDelta)}`,
			`applied overhang ${px(overhang)}`,
			`ua ${navigator.userAgent}`,
		].join('\n')
	)

	async function copyAll() {
		read('copy')
		try {
			await navigator.clipboard.writeText(blob)
			status = 'copied'
			showBlob = false
		} catch {
			// http origins have no clipboard api - fall back to a selectable blob
			showBlob = true
			status = 'no clipboard here: long-press the text below'
			await tick()
			blobEl?.select()
		}
	}
</script>

<div
	class="fixed top-0 right-0 left-0 z-[200] bg-black/85 p-2 font-mono text-[10px] leading-tight text-white"
	role="button"
	tabindex="0"
	onclick={() => void copyAll()}
	onkeydown={(event) => {
		if (event.key === 'Enter' || event.key === ' ') void copyAll()
	}}
>
	<div class="flex justify-between gap-2 text-emerald-300">
		<span>vv debug - #{eventCount} {lastEvent}</span>
		<span>{status}</span>
	</div>
	<div class="mt-1 grid grid-cols-2 gap-x-3">
		<span>innerHeight {px(metrics.innerHeight)}</span>
		<span>scrollY {px(metrics.scrollY)}</span>
		<span>vv.height {px(metrics.vvHeight)}</span>
		<span>vv.offsetTop {px(metrics.vvOffsetTop)}</span>
		<span>vv.pageTop {px(metrics.vvPageTop)}</span>
		<span>vv.scale {metrics.vvScale}</span>
		<span>--app-height {metrics.appHeight}</span>
		<span>visible bottom {px(visibleBottom)}</span>
		<span>shell {px(metrics.shellTop)} / {px(metrics.shellBottom)}</span>
		<span>overlay {px(metrics.overlayTop)} / {px(metrics.overlayBottom)}</span>
		<span class="text-amber-300">shell delta {px(shellDelta)}</span>
		<span class="text-amber-300">overlay delta {px(overlayDelta)}</span>
		<span class="text-emerald-300">overhang {px(overhang)}</span>
	</div>
	{#if showBlob}
		<textarea
			bind:this={blobEl}
			class="mt-1 h-24 w-full bg-black text-white"
			readonly
			value={blob}
		></textarea>
	{/if}
</div>

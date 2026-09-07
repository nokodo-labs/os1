<script module lang="ts">
	/**
	 * anything that can report where it is on screen. a live DOM `Range` is one,
	 * which is what lets the popover follow the selection while the page scrolls
	 * instead of freezing at the point it opened.
	 */
	export interface PopoverAnchor {
		getBoundingClientRect(): DOMRect
	}
</script>

<script lang="ts">
	import { portal } from '$lib/attachments/portal'
	import { fitInside, placeBelow } from '$lib/components/primitives/menuPlacement'
	import { popupMenuScaleTransition } from '$lib/components/primitives/PopupMenu.svelte'
	import type { Snippet } from 'svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		open: boolean
		anchor: PopoverAnchor | null
		onClose: () => void
		ariaLabel: string
		/** used until the panel has been measured once. */
		estimatedHeight?: number
		class?: string
		children: Snippet
	}

	let {
		open,
		anchor,
		onClose,
		ariaLabel,
		estimatedHeight = 120,
		class: className = '',
		children,
	}: Props = $props()

	/** distance kept between the selection and the popover. */
	const ANCHOR_GAP = 8

	let panelEl = $state<HTMLElement | null>(null)
	let top = $state(0)
	let left = $state(0)
	let placed = $state(false)

	function updatePosition(): void {
		if (!anchor) {
			// nothing to anchor to: show it where it is rather than not at all
			placed = true
			return
		}
		const rect = anchor.getBoundingClientRect()
		const height = panelEl?.offsetHeight || estimatedHeight
		const width = panelEl?.offsetWidth ?? 0
		top = placeBelow(rect, height, window.innerHeight, ANCHOR_GAP)
		// centred on the selection rather than edge-anchored: the popover belongs
		// to the words under it, not to a button in a corner.
		left = fitInside(rect.left + rect.width / 2 - width / 2, width, window.innerWidth)
		placed = true
	}

	$effect(() => {
		if (!open) return
		void anchor
		void tick().then(updatePosition)
	})

	$effect(() => {
		if (!open) {
			placed = false
			return
		}
		const reposition = () => updatePosition()
		window.addEventListener('resize', reposition)
		window.addEventListener('scroll', reposition, true)
		return () => {
			window.removeEventListener('resize', reposition)
			window.removeEventListener('scroll', reposition, true)
		}
	})

	$effect(() => {
		const node = panelEl
		if (!open || !node) return
		const observer = new ResizeObserver(updatePosition)
		observer.observe(node)
		return () => observer.disconnect()
	})

	$effect(() => {
		if (!open) return
		const onPointerDown = (event: PointerEvent) => {
			if (panelEl && event.composedPath().includes(panelEl)) return
			onClose()
		}
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key !== 'Escape') return
			event.preventDefault()
			onClose()
		}
		window.addEventListener('pointerdown', onPointerDown)
		window.addEventListener('keydown', onKeyDown)
		return () => {
			window.removeEventListener('pointerdown', onPointerDown)
			window.removeEventListener('keydown', onKeyDown)
		}
	})
</script>

{#if open}
	<div
		{@attach portal()}
		bind:this={panelEl}
		role="dialog"
		aria-label={ariaLabel}
		transition:scale={popupMenuScaleTransition}
		class="fixed z-9999 {className}"
		style="top: {top}px; left: {left}px; visibility: {placed ? 'visible' : 'hidden'};"
	>
		{@render children()}
	</div>
{/if}

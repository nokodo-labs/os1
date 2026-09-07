<script lang="ts">
	import { portal } from '$lib/attachments/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import { fitInside, placeBeside } from '$lib/components/primitives/menuPlacement'
	import { popupMenuScaleTransition } from '$lib/components/primitives/PopupMenu.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Snippet } from 'svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		open: boolean
		anchorEl: HTMLElement | null
		onClose: () => void
		/** desktop submenu hover lifecycle: the anchor opens it, leaving both closes it. */
		openOnHover?: boolean
		/** hover asked for an open; needed for `openOnHover` to do anything. */
		onOpen?: () => void
		class?: string
		estimatedWidth?: number
		estimatedHeight?: number
		children: Snippet
		[key: string]: unknown
	}

	let {
		open,
		anchorEl,
		onClose,
		openOnHover = false,
		onOpen,
		class: className = '',
		estimatedWidth = 240,
		estimatedHeight = 280,
		children,
		...rest
	}: Props = $props()

	/** grace for the gap between anchor and menu only; landing on a sibling item closes at once. */
	const HOVER_CLOSE_DELAY_MS = 120
	/** distance between the anchor row and the menu it opens. */
	const ANCHOR_GAP = 6

	let menuEl = $state<HTMLDivElement | null>(null)
	let posTop = $state(0)
	let posLeft = $state(0)
	let hoverCloseTimer: number | null = null

	const hoverDriven = $derived(openOnHover && device.hasHover && !device.isTouch)

	function cancelHoverClose(): void {
		if (hoverCloseTimer === null) return
		window.clearTimeout(hoverCloseTimer)
		hoverCloseTimer = null
	}

	function updatePosition(): void {
		if (!anchorEl) return
		const rect = anchorEl.getBoundingClientRect()
		const menuWidth = menuEl ? menuEl.offsetWidth : estimatedWidth
		const menuHeight = menuEl ? menuEl.offsetHeight : estimatedHeight
		posLeft = placeBeside(rect, menuWidth, window.innerWidth, ANCHOR_GAP)
		posTop = fitInside(rect.top, menuHeight, window.innerHeight)
	}

	$effect(() => {
		if (!open || !anchorEl) return
		void tick().then(updatePosition)
	})

	$effect(() => {
		if (!open) return
		const onReposition = () => updatePosition()
		window.addEventListener('resize', onReposition)
		window.addEventListener('scroll', onReposition, true)
		return () => {
			window.removeEventListener('resize', onReposition)
			window.removeEventListener('scroll', onReposition, true)
		}
	})

	$effect(() => {
		const node = menuEl
		if (!open || !node) return
		const ro = new ResizeObserver(updatePosition)
		ro.observe(node)
		return () => ro.disconnect()
	})

	$effect(() => {
		if (!open) return
		const onPointerDown = (event: PointerEvent) => {
			const path = event.composedPath()
			if (menuEl && path.includes(menuEl)) return
			if (anchorEl && path.includes(anchorEl)) return
			if (
				path.some(
					(node) => node instanceof HTMLElement && node.closest('[data-popup-menu]')
				)
			) {
				return
			}
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

	$effect(() => {
		const anchor = anchorEl
		if (!hoverDriven || !anchor) return
		const onPointerEnter = (event: PointerEvent) => {
			if (event.pointerType === 'touch') return
			cancelHoverClose()
			onOpen?.()
		}
		anchor.addEventListener('pointerenter', onPointerEnter)
		return () => {
			anchor.removeEventListener('pointerenter', onPointerEnter)
			cancelHoverClose()
		}
	})

	$effect(() => {
		if (!open || !hoverDriven) return
		const onPointerOver = (event: PointerEvent) => {
			if (event.pointerType === 'touch') return
			const path = event.composedPath()
			const inside =
				(menuEl !== null && path.includes(menuEl)) ||
				(anchorEl !== null && path.includes(anchorEl))
			if (inside) {
				cancelHoverClose()
				return
			}
			const onSibling = path.some(
				(node) => node instanceof HTMLElement && node.getAttribute('role') === 'menuitem'
			)
			if (onSibling) {
				cancelHoverClose()
				onClose()
				return
			}
			if (hoverCloseTimer !== null) return
			hoverCloseTimer = window.setTimeout(() => {
				hoverCloseTimer = null
				onClose()
			}, HOVER_CLOSE_DELAY_MS)
		}
		window.addEventListener('pointerover', onPointerOver)
		return () => {
			window.removeEventListener('pointerover', onPointerOver)
			cancelHoverClose()
		}
	})
</script>

{#if open}
	<div
		{@attach portal()}
		bind:this={menuEl}
		role="menu"
		data-popup-menu
		transition:scale={popupMenuScaleTransition}
		class="fixed z-9999"
		style="top: {posTop}px; left: {posLeft}px;"
		{...rest}
	>
		<LiquidMetal
			tag="div"
			class="rounded-popup border-foreground/12 bg-background/80 flex max-h-[min(70vh,28rem)] max-w-[min(calc(100vw-1rem),22rem)] min-w-56 flex-col overflow-y-auto border p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55),inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-[18px] {className}"
		>
			{@render children()}
		</LiquidMetal>
	</div>
{/if}

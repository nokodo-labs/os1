<script module lang="ts">
	export const popupMenuScaleTransition = { duration: 160, start: 0.96, opacity: 0 } as const
</script>

<script lang="ts">
	import { portal } from '$lib/attachments/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import { fitInside, placeBelow } from '$lib/components/primitives/menuPlacement'
	import type { Snippet } from 'svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		open: boolean
		anchorEl: HTMLElement | null
		/** viewport point to open at instead of the anchor, for right-click / hold menus. */
		anchorPoint?: { x: number; y: number } | null
		onClose: () => void
		class?: string
		estimatedHeight?: number
		children: Snippet
		[key: string]: unknown
	}

	let {
		open,
		anchorEl,
		anchorPoint = null,
		onClose,
		class: className = '',
		estimatedHeight = 200,
		children,
		...rest
	}: Props = $props()

	/** distance between the anchor and the menu it opens. */
	const ANCHOR_GAP = 4

	let menuEl = $state<HTMLDivElement | null>(null)
	let posTop = $state(0)
	let posLeft = $state(0)
	let usesLeft = $state(true)

	/** a point anchors as a zero-size rect, so both paths share the flip logic. */
	function anchorRect(): { top: number; bottom: number; left: number; right: number } | null {
		if (anchorPoint) {
			return {
				top: anchorPoint.y,
				bottom: anchorPoint.y,
				left: anchorPoint.x,
				right: anchorPoint.x,
			}
		}
		return anchorEl?.getBoundingClientRect() ?? null
	}

	function updatePosition(): void {
		const rect = anchorRect()
		if (!rect) return
		const menuHeight = menuEl ? menuEl.offsetHeight : estimatedHeight
		const menuWidth = menuEl ? menuEl.offsetWidth : 0
		posTop = placeBelow(rect, menuHeight, window.innerHeight, ANCHOR_GAP)
		// the menu grows away from the nearer edge, so it is offset from that edge
		usesLeft = rect.left < window.innerWidth / 2
		const offset = usesLeft ? rect.left : window.innerWidth - rect.right
		posLeft = fitInside(offset, menuWidth, window.innerWidth)
	}

	$effect(() => {
		if (!open || (!anchorPoint && !anchorEl)) return
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
		const onPointerDown = (e: PointerEvent) => {
			const path = e.composedPath()
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
		const onKeyDown = (e: KeyboardEvent) => {
			if (e.key !== 'Escape') return
			e.preventDefault()
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
		bind:this={menuEl}
		role="menu"
		data-popup-menu
		transition:scale={popupMenuScaleTransition}
		class="fixed z-9999"
		style="top: {posTop}px; {usesLeft ? `left: ${posLeft}px` : `right: ${posLeft}px`};"
		{...rest}
	>
		<LiquidMetal
			tag="div"
			class="rounded-popup border-foreground/12 bg-background/80 flex max-w-[min(calc(100vw-1rem),22rem)] min-w-44 flex-col overflow-hidden border p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55),inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-[18px] {className}"
		>
			{@render children()}
		</LiquidMetal>
	</div>
{/if}

<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import { popupMenuScaleTransition } from '$lib/components/primitives/PopupMenu.svelte'
	import type { Snippet } from 'svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		open: boolean
		anchorEl: HTMLElement | null
		onClose: () => void
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
		class: className = '',
		estimatedWidth = 240,
		estimatedHeight = 280,
		children,
		...rest
	}: Props = $props()

	let menuEl = $state<HTMLDivElement | null>(null)
	let posTop = $state(0)
	let posLeft = $state(0)
	let usesRightSide = $state(true)

	function updatePosition(): void {
		if (!anchorEl) return
		const rect = anchorEl.getBoundingClientRect()
		const menuWidth = menuEl ? menuEl.offsetWidth : estimatedWidth
		const menuHeight = menuEl ? menuEl.offsetHeight : estimatedHeight
		usesRightSide = rect.right + menuWidth + 8 < window.innerWidth || rect.left < menuWidth + 8
		posLeft = usesRightSide ? rect.right + 6 : Math.max(6, rect.left - menuWidth - 6)
		posTop = Math.min(Math.max(6, rect.top), Math.max(6, window.innerHeight - menuHeight - 6))
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
</script>

{#if open}
	<div
		use:portal
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
			class="rounded-popup border-foreground/12 bg-background/80 max-h-[min(70vh,28rem)] max-w-[min(calc(100vw-1rem),22rem)] min-w-56 overflow-y-auto border p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55),inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-[18px] {className}"
		>
			{@render children()}
		</LiquidMetal>
	</div>
{/if}

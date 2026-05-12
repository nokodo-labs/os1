<script module lang="ts">
	export const popupMenuScaleTransition = { duration: 160, start: 0.96, opacity: 0 } as const
</script>

<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import type { Snippet } from 'svelte'
	import { tick } from 'svelte'
	import { scale } from 'svelte/transition'

	interface Props {
		open: boolean
		anchorEl: HTMLElement | null
		onClose: () => void
		class?: string
		estimatedHeight?: number
		children: Snippet
		[key: string]: unknown
	}

	let {
		open,
		anchorEl,
		onClose,
		class: className = '',
		estimatedHeight = 200,
		children,
		...rest
	}: Props = $props()

	let menuEl = $state<HTMLDivElement | null>(null)
	let posTop = $state(0)
	let posLeft = $state(0)
	let usesLeft = $state(true)

	function updatePosition(): void {
		if (!anchorEl) return
		const rect = anchorEl.getBoundingClientRect()
		const mh = menuEl ? menuEl.offsetHeight : estimatedHeight
		const screenCx = window.innerWidth / 2
		posTop =
			rect.bottom + mh < window.innerHeight ? rect.bottom + 4 : Math.max(4, rect.top - mh - 4)
		usesLeft = rect.left < screenCx
		posLeft = usesLeft ? rect.left : window.innerWidth - rect.right
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
		use:portal
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
			class="rounded-popup border-foreground/12 bg-background/80 max-w-[min(calc(100vw-1rem),22rem)] min-w-44 overflow-hidden border p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55),inset_0_1px_0_rgb(255_255_255/0.12)] backdrop-blur-[18px] {className}"
		>
			{@render children()}
		</LiquidMetal>
	</div>
{/if}

<script lang="ts">
	import { portal } from '$lib/actions/portal'
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

	$effect(() => {
		if (!open || !anchorEl) return
		void tick().then(() => {
			if (!anchorEl) return
			const rect = anchorEl.getBoundingClientRect()
			const mh = menuEl ? menuEl.offsetHeight : estimatedHeight
			const screenCx = window.innerWidth / 2
			posTop =
				rect.bottom + mh < window.innerHeight
					? rect.bottom + 4
					: Math.max(4, rect.top - mh - 4)
			usesLeft = rect.left < screenCx
			posLeft = usesLeft ? rect.left : window.innerWidth - rect.right
		})
	})

	$effect(() => {
		if (!open) return
		const onPointerDown = (e: PointerEvent) => {
			const path = e.composedPath()
			if (menuEl && path.includes(menuEl)) return
			if (anchorEl && path.includes(anchorEl)) return
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
		transition:scale={{ duration: 160, start: 0.96, opacity: 0 }}
		class="liquid-metal fixed z-9999 min-w-44 rounded-3xl p-2 shadow-[0_24px_48px_rgba(12,10,30,0.55)] {className}"
		style="top: {posTop}px; {usesLeft ? `left: ${posLeft}px` : `right: ${posLeft}px`};"
		{...rest}
	>
		{@render children()}
	</div>
{/if}

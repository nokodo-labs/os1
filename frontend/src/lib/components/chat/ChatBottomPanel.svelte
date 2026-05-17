<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import LiquidMetal from '$lib/components/effects/LiquidMetal.svelte'
	import { device } from '$lib/stores/device.svelte'
	import type { Snippet } from 'svelte'
	import { cubicOut } from 'svelte/easing'
	import { fly } from 'svelte/transition'

	interface Props {
		open: boolean
		onClose: () => void
		ariaLabel: string
		children: Snippet
		class?: string
	}

	let {
		open,
		onClose,
		ariaLabel,
		children,
		class: panelClass = 'add-context-panel',
	}: Props = $props()

	let dragStartY = $state(0)
	let dragCurrentY = $state(0)
	let isDragging = $state(false)
	let dragPointerId = $state<number | null>(null)

	const dragOffsetY = $derived(isDragging ? Math.max(0, dragCurrentY - dragStartY) : 0)
	const DRAG_CLOSE_THRESHOLD = 80

	function onHandlePointerDown(event: PointerEvent) {
		dragPointerId = event.pointerId
		dragStartY = event.clientY
		dragCurrentY = event.clientY
		isDragging = true
		;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
	}

	function onHandlePointerMove(event: PointerEvent) {
		if (!isDragging || event.pointerId !== dragPointerId) return
		dragCurrentY = event.clientY
	}

	function onHandlePointerUp(event: PointerEvent) {
		if (!isDragging || event.pointerId !== dragPointerId) return
		const delta = event.clientY - dragStartY
		isDragging = false
		dragPointerId = null
		if (delta > DRAG_CLOSE_THRESHOLD) onClose()
	}

	function onHandlePointerCancel(event: PointerEvent) {
		if (event.pointerId !== dragPointerId) return
		isDragging = false
		dragPointerId = null
	}

	function handlePanelKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.stopPropagation()
			onClose()
		}
	}
</script>

{#if open}
	<div use:portal>
		<div
			class="fixed inset-0 z-40"
			role="button"
			tabindex="-1"
			aria-label="close {ariaLabel}"
			onclick={onClose}
			onkeydown={(event) => event.key === 'Escape' && onClose()}
		></div>

		<div
			role="dialog"
			aria-label={ariaLabel}
			aria-modal="true"
			tabindex="-1"
			class="pointer-events-none fixed right-0 bottom-0 z-50"
			style="left: var(--island-left, 0);"
			in:fly={{ y: 480, duration: 400, easing: cubicOut }}
			out:fly={{ y: 480, duration: 280, easing: cubicOut }}
			onkeydown={handlePanelKeyDown}
		>
			<div
				class="pointer-events-auto mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x); transform: translateY({dragOffsetY}px); transition: {isDragging
					? 'none'
					: 'transform 0.2s ease'};"
			>
				<LiquidMetal
					cornerRadius={24}
					class={panelClass}
					style="border-radius: var(--radius-popup) var(--radius-popup) 0 0; overflow: hidden;"
				>
					<div class="relative z-10 pb-12">
						<div
							class="flex cursor-grab justify-center pt-3 pb-2 active:cursor-grabbing"
							role="button"
							tabindex="0"
							aria-label="drag to close"
							style="touch-action: none;"
							onpointerdown={onHandlePointerDown}
							onpointermove={onHandlePointerMove}
							onpointerup={onHandlePointerUp}
							onpointercancel={onHandlePointerCancel}
							onkeydown={(event) => event.key === 'Enter' && onClose()}
						>
							<div class="bg-foreground/25 h-1 w-10 rounded-full"></div>
						</div>

						{@render children()}
					</div>
				</LiquidMetal>
			</div>
		</div>
	</div>
{/if}

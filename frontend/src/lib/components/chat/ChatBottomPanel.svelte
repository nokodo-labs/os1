<script lang="ts">
	import { portal } from '$lib/attachments/portal'
	import { panelDrag } from '$lib/attachments/paneldrag'
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

	const reduceMotion = $derived(device.prefersReducedMotion)

	// a dragged-out panel has already flown off under the finger's momentum;
	// letting svelte fly it a second time would rewind it first
	let flungOut = $state(false)
	$effect(() => {
		if (open) flungOut = false
	})

	const enterMs = $derived(reduceMotion ? 0 : 400)
	const exitMs = $derived(flungOut || reduceMotion ? 0 : 280)

	function dismissByDrag(): void {
		flungOut = true
		onClose()
	}

	function handlePanelKeyDown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			event.stopPropagation()
			onClose()
		}
	}
</script>

{#if open}
	<div {@attach portal()}>
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
			in:fly={{ y: 480, duration: enterMs, easing: cubicOut }}
			out:fly={{ y: 480, duration: exitMs, easing: cubicOut }}
			onkeydown={handlePanelKeyDown}
		>
			<div
				class="pointer-events-auto mx-auto w-full {device.isMobile ? '' : 'max-w-7xl'}"
				style="padding-left: var(--spacing-page-x); padding-right: var(--spacing-page-x);"
				{@attach panelDrag({
					onDismiss: dismissByDrag,
					reducedMotion: () => reduceMotion,
				})}
			>
				<LiquidMetal
					cornerRadius={24}
					class={panelClass}
					style="border-radius: var(--radius-popup) var(--radius-popup) 0 0; overflow: hidden;"
				>
					<div class="relative z-10 flex max-h-[82dvh] flex-col">
						<div
							class="flex shrink-0 cursor-grab justify-center pt-3 pb-2 active:cursor-grabbing"
							role="button"
							tabindex="0"
							aria-label="drag to close"
							style="touch-action: none;"
							onkeydown={(event) => event.key === 'Enter' && onClose()}
							data-panel-handle
						>
							<div class="bg-foreground/25 h-1 w-10 rounded-full"></div>
						</div>

						<div class="min-h-0 flex-1 overflow-y-auto overscroll-contain pb-12">
							{@render children()}
						</div>
					</div>
				</LiquidMetal>
			</div>
		</div>
	</div>
{/if}

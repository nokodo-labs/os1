<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import XMark from '$lib/components/icons/XMark.svelte'
	import { cubicOut, quintOut } from 'svelte/easing'
	import { fade, scale } from 'svelte/transition'

	interface AppModalProps {
		open: boolean
		title: string
		description?: string
		onClose: () => void
		widthClassName?: string
	}

	let {
		open,
		title,
		onClose,
		widthClassName = 'max-w-xl',
		children,
	}: AppModalProps & { children?: import('svelte').Snippet } = $props()

	function onKeyDown(event: KeyboardEvent) {
		if (event.key !== 'Escape') return
		event.preventDefault()
		onClose()
	}

	/**
	 * stop pointerdown from bubbling to global listeners (e.g., menu close handlers).
	 * this ensures clicking inside the modal doesn't close menus that spawned it.
	 */
	function onPointerDown(event: PointerEvent) {
		event.stopPropagation()
	}

	$effect(() => {
		if (!open) return
		document.addEventListener('keydown', onKeyDown)
		return () => document.removeEventListener('keydown', onKeyDown)
	})
</script>

{#if open}
	<div
		use:portal
		class="fixed inset-0 z-50 flex items-center justify-center px-3 sm:px-4"
		style="padding-top: max(1rem, env(safe-area-inset-top)); padding-bottom: max(1rem, env(safe-area-inset-bottom));"
		role="presentation"
		onpointerdown={onPointerDown}
	>
		<!-- backdrop (fades independently, click closes modal) -->
		<button
			type="button"
			class="absolute inset-0 bg-black/18 backdrop-blur-sm dark:bg-black/30"
			transition:fade={{ duration: 180, easing: cubicOut }}
			onmousedown={onClose}
			aria-label="close modal"
			tabindex="-1"
		></button>

		<!-- dialog panel -->
		<div
			class="relative max-h-[calc(100dvh-2rem)] w-full {widthClassName} rounded-container border-border/60 bg-card/88 text-card-foreground overflow-hidden border shadow-[0_24px_48px_rgba(15,23,42,0.16)] backdrop-blur-xl will-change-transform dark:shadow-[0_32px_64px_rgba(12,10,30,0.55)]"
			role="dialog"
			aria-modal="true"
			aria-label={title}
			transition:scale={{ duration: 220, start: 0.96, opacity: 0, easing: quintOut }}
		>
			<div class="relative z-10 flex max-h-[calc(100dvh-2rem)] min-h-0 flex-col">
				<header class="flex shrink-0 items-start justify-between gap-3 px-4 pt-4 pb-2">
					<div class="flex min-h-9 min-w-0 items-center">
						<div class="text-card-foreground pl-3 text-lg font-semibold">
							{title}
						</div>
					</div>
					<button
						type="button"
						class="text-muted-foreground hover:text-foreground flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent transition-all duration-150 hover:scale-[1.05] active:scale-[0.97]"
						onclick={onClose}
						aria-label="close"
					>
						<XMark class="h-5 w-5" />
					</button>
				</header>

				<div class="min-h-0 flex-1 overflow-y-auto px-4 pb-6">
					{@render children?.()}
				</div>
			</div>
		</div>
	</div>
{/if}

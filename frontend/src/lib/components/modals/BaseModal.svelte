<script lang="ts">
	import { portal } from '$lib/actions/portal'
	import XMark from '$lib/components/icons/XMark.svelte'
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
		description,
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
		class="fixed inset-0 z-50 flex items-center justify-center p-4"
		role="presentation"
		onpointerdown={onPointerDown}
	>
		<!-- backdrop (fades independently, click closes modal) -->
		<button
			type="button"
			class="absolute inset-0 bg-black/18 backdrop-blur-sm dark:bg-black/30"
			transition:fade={{ duration: 180 }}
			onmousedown={onClose}
			aria-label="close modal"
			tabindex="-1"
		></button>

		<!-- dialog panel -->
		<div
			class="relative w-full {widthClassName} rounded-container max-h-[calc(100vh-2rem)] overflow-hidden border border-black/10 bg-white/88 text-black shadow-[0_24px_48px_rgba(15,23,42,0.16)] backdrop-blur-xl dark:border-white/10 dark:bg-black/75 dark:text-white dark:shadow-[0_32px_64px_rgba(12,10,30,0.55)]"
			role="dialog"
			aria-modal="true"
			aria-label={title}
			transition:scale={{ duration: 240, start: 0.94, opacity: 0 }}
		>
			<div class="relative z-10 flex max-h-[calc(100vh-2rem)] flex-col p-6">
				<header class="mb-5 flex items-start justify-between gap-3">
					<div class="min-w-0">
						<div class="text-lg font-semibold text-black/90 dark:text-white/95">
							{title}
						</div>
						{#if description}
							<div class="mt-1 text-sm text-black/60 dark:text-white/60">
								{description}
							</div>
						{/if}
					</div>
					<button
						type="button"
						class="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent text-black/60 transition-all duration-150 hover:scale-[1.05] hover:text-black active:scale-[0.97] dark:text-white/70 dark:hover:text-white"
						onclick={onClose}
						aria-label="close"
					>
						<XMark class="h-5 w-5" />
					</button>
				</header>

				<div class="min-h-0 overflow-y-auto">
					{@render children?.()}
				</div>
			</div>
		</div>
	</div>
{/if}

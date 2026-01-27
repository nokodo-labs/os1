<script lang="ts">
	import { portal } from '$lib/actions/portal'

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

	function onBackdropMouseDown(event: MouseEvent) {
		if (event.target !== event.currentTarget) return
		onClose()
	}

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
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
		role="presentation"
		onmousedown={onBackdropMouseDown}
		onpointerdown={onPointerDown}
	>
		<div
			class="liquid-glass w-full {widthClassName} rounded-container max-h-[calc(100vh-2rem)] overflow-hidden shadow-[0_32px_64px_rgba(12,10,30,0.55)]"
			role="dialog"
			aria-modal="true"
			aria-label={title}
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content flex max-h-[calc(100vh-2rem)] flex-col p-6">
				<header class="mb-5">
					<div class="text-lg font-semibold text-white/95">{title}</div>
					{#if description}
						<div class="mt-1 text-sm text-white/60">{description}</div>
					{/if}
				</header>

				<div class="min-h-0 overflow-y-auto">
					{@render children?.()}
				</div>
			</div>
		</div>
	</div>
{/if}

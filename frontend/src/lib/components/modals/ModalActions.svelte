<script module lang="ts">
	// the one definition for buttons that sit in a modal action row: the shared
	// shape, plus the three fills the modals actually use (share/cancel, delete,
	// primary). `ModalSaveButton` carries its own copy of the primary fill.
	export const modalActionButtonClass =
		'rounded-pill inline-flex min-h-9 cursor-pointer items-center justify-center gap-1.5 px-4 text-sm font-semibold transition-all duration-150 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-55'
	export const modalQuietButtonClass = `${modalActionButtonClass} border-foreground/12 text-foreground/80 hover:bg-foreground/6 border bg-transparent`
	export const modalDangerButtonClass = `${modalActionButtonClass} border border-red-500/30 bg-red-500/13 text-red-300`
	export const modalPrimaryButtonClass = `${modalActionButtonClass} bg-(--accent-primary) text-white hover:brightness-[1.06]`
</script>

<script lang="ts">
	import type { Snippet } from 'svelte'

	interface ModalActionsProps {
		/** supporting actions: left of the primary on wide viewports, under it when stacked */
		leading?: Snippet
		/** primary action(s): right-aligned on wide viewports, on top when stacked */
		children?: Snippet
		class?: string
	}

	let { leading, children, class: className = '' }: ModalActionsProps = $props()

	// the one layout rule for modal action rows. wide: a right-aligned row with an
	// optional leading group. phone: full-width buttons stacked, primary on top
	// (col-reverse), supporting actions last.
	const groupClass =
		'flex flex-wrap items-center gap-2 max-[520px]:flex-col max-[520px]:items-stretch max-[520px]:*:w-full max-[520px]:*:justify-center'
</script>

<div
	class="flex flex-wrap items-center gap-2 max-[520px]:flex-col-reverse max-[520px]:items-stretch {className}"
>
	{#if leading}
		<div class={groupClass}>
			{@render leading()}
		</div>
	{/if}
	<div class="{groupClass} flex-1 justify-end">
		{@render children?.()}
	</div>
</div>

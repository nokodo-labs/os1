<script lang="ts">
	/**
	 * overflow menu for a person row, used where the row's actions do not fit
	 * beside it. each row owns its own instance because the popup anchors to
	 * its own button.
	 *
	 * the whole row opens this same menu on right-click and on touch hold: mark
	 * the row element `data-row` and the menu finds it from its own trigger.
	 * the marker, rather than a prop, is what rows rendered inline in an
	 * `{#each}` can give without per-row state.
	 */

	import { contextmenu, type ContextMenuAnchor } from '$lib/attachments/contextmenu'
	import EllipsisHorizontal from '$lib/components/icons/EllipsisHorizontal.svelte'
	import { PopupMenu } from '$lib/components/primitives'
	import type { Snippet } from 'svelte'

	interface Props {
		/** receives a closer, so an item can dismiss the menu before it acts. */
		children: Snippet<[() => void]>
		label?: string
	}

	let { children, label = 'options' }: Props = $props()

	let open = $state(false)
	let anchorEl = $state<HTMLButtonElement | null>(null)
	let anchorPoint = $state<ContextMenuAnchor | null>(null)

	$effect(() => {
		const row = anchorEl?.closest('[data-row]')
		if (!(row instanceof HTMLElement)) return
		return contextmenu({
			onOpen: (anchor) => {
				anchorPoint = anchor
				open = true
			},
		})(row)
	})

	function close(): void {
		open = false
	}
</script>

<button
	type="button"
	bind:this={anchorEl}
	class="text-foreground/65 hover:bg-foreground/8 hover:text-foreground flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full border-none bg-transparent transition-all duration-150 active:scale-[0.97]"
	onclick={(event) => {
		event.stopPropagation()
		anchorPoint = null
		open = !open
	}}
	aria-label={label}
	aria-haspopup="menu"
	aria-expanded={open}
>
	<EllipsisHorizontal class="size-5" />
</button>

<PopupMenu {open} {anchorEl} {anchorPoint} onClose={close} class="min-w-44">
	{@render children(close)}
</PopupMenu>

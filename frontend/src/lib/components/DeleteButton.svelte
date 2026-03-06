<script lang="ts">
	import Trash from '$lib/components/icons/Trash.svelte'
	import { modals } from '$lib/stores/modals.svelte'

	export type DeleteModalText = {
		title: string
		description?: string
	}

	interface Props {
		confirm?: boolean
		modalText?: DeleteModalText
		onDelete: () => void | boolean | Promise<void | boolean>
		label?: string
		onTrigger?: () => void
		stopPropagation?: boolean
		showTrigger?: boolean
		open?: boolean
	}

	let {
		confirm = true,
		modalText = { title: 'delete?' },
		onDelete,
		label = 'delete',
		onTrigger,
		stopPropagation = false,
		showTrigger = true,
		open = $bindable(false),
	}: Props = $props()

	// when open is set externally (e.g. showTrigger=false), open the confirm modal
	$effect(() => {
		if (!open) return
		open = false
		modals.open('confirm-delete', { ...modalText, onDelete })
	})

	async function runDelete(): Promise<void> {
		await onDelete()
	}

	function handleTriggerClick(event: MouseEvent): void {
		if (stopPropagation) event.stopPropagation()
		onTrigger?.()
		if (confirm) {
			modals.open('confirm-delete', { ...modalText, onDelete })
			return
		}
		void runDelete()
	}
</script>

{#if showTrigger}
	<button
		type="button"
		class="group rounded-pill text-foreground/80 flex w-full cursor-pointer items-center border-none bg-transparent px-3 py-2 text-left text-sm transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300"
		onclick={handleTriggerClick}
	>
		<Trash
			class="h-4 w-4 text-red-400 transition-colors duration-150 group-hover:text-red-300"
		/>
		<span class="ml-2">{label}</span>
	</button>
{/if}

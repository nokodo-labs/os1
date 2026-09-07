<script lang="ts">
	import Trash from '$lib/components/icons/Trash.svelte'
	import MenuItem from '$lib/components/primitives/MenuItem.svelte'
	import { modals, type ConfirmDeleteToggle } from '$lib/stores/modals.svelte'

	export type DeleteModalText = {
		title: string
		description?: string
	}

	interface Props {
		confirm?: boolean
		modalText?: DeleteModalText
		/** optional opt-in switch shown in the confirm dialog. */
		modalToggle?: ConfirmDeleteToggle
		onDelete: (toggleOn: boolean) => void | boolean | Promise<void | boolean>
		label?: string
		onTrigger?: () => void
		stopPropagation?: boolean
		showTrigger?: boolean
		open?: boolean
		variant?: 'menu' | 'icon'
		disabled?: boolean
	}

	let {
		confirm = true,
		modalText = { title: 'delete?' },
		modalToggle,
		onDelete,
		label = 'delete',
		onTrigger,
		stopPropagation = false,
		showTrigger = true,
		open = $bindable(false),
		variant = 'menu',
		disabled = false,
	}: Props = $props()

	// when open is set externally (e.g. showTrigger=false), open the confirm modal
	$effect(() => {
		if (!open) return
		open = false
		modals.open('confirm-delete', { ...modalText, toggle: modalToggle, onDelete })
	})

	async function runDelete(): Promise<void> {
		await onDelete(false)
	}

	function handleTriggerClick(event: MouseEvent): void {
		if (stopPropagation) event.stopPropagation()
		onTrigger?.()
		if (confirm) {
			modals.open('confirm-delete', { ...modalText, toggle: modalToggle, onDelete })
			return
		}
		void runDelete()
	}
</script>

{#if showTrigger}
	{#if variant === 'menu'}
		<MenuItem destructive icon={Trash} {disabled} onclick={handleTriggerClick}>
			{label}
		</MenuItem>
	{:else}
		<button
			type="button"
			class="rounded-circle text-foreground/40 flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center border-none bg-transparent transition-colors duration-150 hover:bg-red-500/10 hover:text-red-300 disabled:cursor-not-allowed disabled:opacity-40"
			{disabled}
			onclick={handleTriggerClick}
			aria-label={label}
			title={label}
		>
			<Trash class="h-4 w-4 text-red-400 transition-colors duration-150" />
		</button>
	{/if}
{/if}

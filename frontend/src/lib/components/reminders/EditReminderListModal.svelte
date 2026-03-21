<script lang="ts">
	import BaseModal from '$lib/components/modals/BaseModal.svelte'
	import type { ReminderListWithCounts } from '$lib/stores/reminders.svelte'

	interface Props {
		open: boolean
		list: ReminderListWithCounts | null
		onClose: () => void
	}

	let { open, list, onClose }: Props = $props()
</script>

<BaseModal
	{open}
	title="edit reminder list"
	description="modal contents coming soon"
	{onClose}
	widthClassName="max-w-lg"
>
	{#if list}
		<div class="space-y-2">
			<div class="text-foreground/70 text-sm">id: {list.id}</div>
			<div class="text-foreground/70 text-sm">name: {list.name}</div>
		</div>
	{/if}
</BaseModal>

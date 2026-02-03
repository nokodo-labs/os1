<script lang="ts">
	import BaseModal from '$lib/components/modals/BaseModal.svelte'

	interface ArchivedChatsModalProps {
		open: boolean
		onClose: () => void
	}

	let { open, onClose }: ArchivedChatsModalProps = $props()

	type ArchivedChat = {
		id: string
		title: string
		summary: string
		archivedAt: string
	}

	const archivedChats: ArchivedChat[] = [
		{
			id: 'a-1',
			title: 'prototype backlog',
			summary: 'next steps for search + modals',
			archivedAt: 'today',
		},
		{
			id: 'a-2',
			title: 'design exploration',
			summary: 'liquid glass + motion notes',
			archivedAt: 'yesterday',
		},
	]
</script>

<BaseModal
	{open}
	title="archived chats"
	description="browse and restore archived threads"
	{onClose}
	widthClassName="max-w-3xl"
>
	<div class="space-y-3">
		{#if archivedChats.length === 0}
			<div class="rounded-pill bg-white/5 p-4 text-sm text-white/60">no archived chats</div>
		{:else}
			<div class="space-y-2">
				{#each archivedChats as chat (chat.id)}
					<button
						type="button"
						class="rounded-pill flex w-full items-start justify-between gap-4 border-none bg-white/5 px-4 py-3 text-left transition-colors hover:bg-white/8"
					>
						<div class="min-w-0">
							<div class="truncate text-sm font-semibold text-white/85">
								{chat.title}
							</div>
							<div class="truncate text-sm text-white/55">{chat.summary}</div>
						</div>
						<div class="shrink-0 text-xs text-white/45">{chat.archivedAt}</div>
					</button>
				{/each}
			</div>
		{/if}

		<div class="flex justify-end">
			<button
				type="button"
				class="rounded-pill border-none bg-white/10 px-4 py-2 text-sm font-semibold text-white/85 transition-colors hover:bg-white/15"
				onclick={onClose}
			>
				close
			</button>
		</div>
	</div>
</BaseModal>

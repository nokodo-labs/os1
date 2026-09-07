<script lang="ts">
	/**
	 * a card holding one run of conversation rows. the rows carry no background
	 * of their own - this card is it, and hairlines inset past the avatar are
	 * what separates them.
	 */

	import ConversationCard from '$lib/components/messages/ConversationCard.svelte'
	import ConversationRow from '$lib/components/messages/ConversationRow.svelte'
	import type { Thread } from '$lib/stores/chat.svelte'

	interface Props {
		label?: string
		threads: readonly Thread[]
		unreadCountOf: (threadId: string) => number
		onOpen: (threadId: string) => void
		onRemoved: (threadId: string) => void
	}

	let { label, threads, unreadCountOf, onOpen, onRemoved }: Props = $props()
</script>

<ConversationCard {label}>
	<div role="list">
		{#each threads as thread, index (thread.id)}
			<ConversationRow
				{thread}
				unreadCount={unreadCountOf(thread.id)}
				dividerAbove={index > 0}
				{onOpen}
				{onRemoved}
			/>
		{/each}
	</div>
</ConversationCard>

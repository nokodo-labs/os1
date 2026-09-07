<script lang="ts">
	/**
	 * the identity of a conversation as it sits in the island: its faces beside its
	 * name, tapped to open the chat info modal. the iMessage header, in glass.
	 */

	import ConversationAvatar from '$lib/components/messages/ConversationAvatar.svelte'
	import type { ConversationDisplay } from '$lib/utils/conversationDisplay'

	interface Props {
		display: ConversationDisplay
		onOpen: () => void
	}

	let { display, onOpen }: Props = $props()

	// a name alone reads as the conversation; only a group's size earns a second line.
	const memberLine = $derived(
		display.isGroup
			? `${display.humanCount} ${display.humanCount === 1 ? 'person' : 'people'}`
			: null
	)
</script>

<button
	type="button"
	class="hover:bg-foreground/8 flex h-11 max-w-[40vw] min-w-0 cursor-pointer items-center gap-2.5 rounded-full border-none bg-transparent py-1 pr-3.5 pl-1 text-left active:scale-[0.97]"
	onclick={onOpen}
	aria-label="chat info"
	title={display.title}
	data-conversation-identity
>
	<span
		class="ring-foreground/12 shrink-0 rounded-full shadow-[0_1px_4px_rgb(0_0_0/0.18)] ring-1 ring-inset"
	>
		<ConversationAvatar
			faces={display.faces}
			isGroup={display.isGroup}
			sizeClass="size-9"
			textClass="text-[0.7rem]"
		/>
	</span>
	<span class="flex min-w-0 flex-col justify-center">
		<span class="text-foreground/95 min-w-0 truncate text-sm leading-tight font-semibold">
			{display.title}
		</span>
		{#if memberLine}
			<span class="text-foreground/45 min-w-0 truncate text-[0.68rem] leading-tight">
				{memberLine}
			</span>
		{/if}
	</span>
</button>

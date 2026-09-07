<script lang="ts">
	import QueueList from '$lib/components/icons/QueueList.svelte'
	import { MenuItem, MenuSectionHeader, PopupMenu } from '$lib/components/primitives'
	import {
		CONVERSATION_GROUPINGS,
		DEFAULT_CONVERSATION_GROUPING,
		groupingById,
		type ConversationGroupingId,
	} from '$lib/messages/grouping'

	interface Props {
		value: ConversationGroupingId
		onSelect: (id: ConversationGroupingId) => void
	}

	let { value, onSelect }: Props = $props()

	let open = $state(false)
	let buttonEl = $state<HTMLButtonElement | null>(null)

	const active = $derived(groupingById(value))
	// resting state wears the group-by glyph itself; an active grouping wears its own icon
	const isGrouped = $derived(value !== DEFAULT_CONVERSATION_GROUPING)
	const ActiveIcon = $derived(isGrouped ? active.icon : QueueList)

	function select(id: ConversationGroupingId): void {
		open = false
		onSelect(id)
	}
</script>

<!-- a composite island control: the wrapper keeps the label shrinkable, which the
     island's own `> button` rules (fixed basis, fixed glyph size) would not allow -->
<span class="flex h-full min-w-0 items-center">
	<button
		type="button"
		bind:this={buttonEl}
		class="rounded-pill flex min-w-0 cursor-pointer items-center border-none bg-transparent opacity-80 transition-all duration-150 hover:scale-[1.05] hover:opacity-100 active:scale-[0.97]"
		onclick={() => (open = !open)}
		aria-label={isGrouped ? `group by: ${active.label}` : 'group by'}
		aria-haspopup="menu"
		aria-expanded={open}
	>
		<ActiveIcon
			class="size-(--island-control-icon-size) shrink-0"
			strokeWidth="2"
			variant={isGrouped ? 'solid' : 'outline'}
		/>
		{#if isGrouped}
			<span class="min-w-0 truncate pr-1.5 pl-1 text-xs font-medium">{active.label}</span>
		{/if}
	</button>
</span>

<PopupMenu {open} anchorEl={buttonEl} onClose={() => (open = false)} class="min-w-48">
	<MenuSectionHeader icon={QueueList}>group by</MenuSectionHeader>
	{#each CONVERSATION_GROUPINGS as grouping (grouping.id)}
		<MenuItem
			icon={grouping.icon}
			selected={value === grouping.id}
			onclick={() => select(grouping.id)}
		>
			{grouping.label}
		</MenuItem>
	{/each}
</PopupMenu>

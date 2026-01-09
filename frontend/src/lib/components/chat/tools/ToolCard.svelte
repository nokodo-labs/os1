<script lang="ts">
	import type { ToolExecution } from '$lib/tools'
	import CustomToolCard from './CustomToolCard.svelte'
	import MemoryRecallToolCard from './MemoryRecallToolCard.svelte'
	import NotificationToolCard from './NotificationToolCard.svelte'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()

	const toolName = $derived(execution.toolCall.name)
</script>

{#if toolName === 'send_notification'}
	<NotificationToolCard {execution} {compact} />
{:else if toolName === 'memory_recall'}
	<MemoryRecallToolCard {execution} {compact} />
{:else}
	<CustomToolCard {execution} {compact} />
{/if}

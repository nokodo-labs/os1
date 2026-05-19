<script lang="ts">
	import Brain from '$lib/components/icons/Brain.svelte'
	import { formatToolEventLine, type ToolExecution } from '$lib/tools'
	import BaseToolCard from './BaseToolCard.svelte'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()

	let recallQuery = $derived(
		typeof execution.toolCall.arguments.query === 'string'
			? execution.toolCall.arguments.query
			: null
	)

	let memories = $derived(
		(() => {
			if (!execution.result || execution.result.isError) return []
			try {
				const parsed = JSON.parse(execution.result.output)
				if (Array.isArray(parsed)) return parsed
				return []
			} catch {
				return []
			}
		})()
	)
</script>

<BaseToolCard {execution} {compact}>
	{#snippet icon()}
		<Brain
			className={`h-4 w-4 text-foreground/80 ${execution.status === 'running' ? 'animate-pulse' : ''}`}
		/>
	{/snippet}

	{#snippet body()}
		{#if recallQuery}
			<div class="text-foreground/60 mb-3 text-sm">
				<span class="text-foreground/50">searching for:</span>
				{recallQuery}
			</div>
		{/if}

		{#if memories.length > 0}
			<div class="space-y-2">
				{#each memories as memory, idx (idx)}
					<div class="rounded-pill bg-foreground/5 text-foreground/70 px-3 py-2 text-sm">
						{typeof memory === 'string' ? memory : JSON.stringify(memory)}
					</div>
				{/each}
			</div>
		{:else if execution.status === 'completed' && !execution.result?.isError}
			<div class="text-foreground/50 text-sm">no memories found</div>
		{/if}

		{#if execution.events.length > 0}
			<div class="mt-3 space-y-1">
				{#each execution.events as event (event.id)}
					<div class="text-foreground/60 flex items-start gap-2 text-xs">
						<span class="text-foreground/45"
							>{event.timestamp.toLocaleTimeString()}</span
						>
						<span>{formatToolEventLine(event)}</span>
					</div>
				{/each}
			</div>
		{/if}

		{#if execution.status === 'error' && execution.error}
			<div class="mt-3 text-sm text-red-300">{execution.error}</div>
		{/if}
	{/snippet}
</BaseToolCard>

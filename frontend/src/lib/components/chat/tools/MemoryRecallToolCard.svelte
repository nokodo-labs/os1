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
			className={`h-4 w-4 text-white/80 ${execution.status === 'running' ? 'animate-pulse' : ''}`}
		/>
	{/snippet}

	{#snippet body()}
		{#if recallQuery}
			<div class="mb-3 text-sm text-white/60">
				<span class="text-white/50">searching for:</span> "{recallQuery}"
			</div>
		{/if}

		{#if memories.length > 0}
			<div class="space-y-2">
				{#each memories as memory, idx (idx)}
					<div class="rounded-pill bg-white/5 px-3 py-2 text-sm text-white/70">
						{typeof memory === 'string' ? memory : JSON.stringify(memory)}
					</div>
				{/each}
			</div>
		{:else if execution.status === 'completed' && !execution.result?.isError}
			<div class="text-sm text-white/50">no memories found</div>
		{/if}

		{#if execution.events.length > 0}
			<div class="mt-3 space-y-1">
				{#each execution.events as event (event.id)}
					<div class="flex items-start gap-2 text-xs text-white/60">
						<span class="text-white/45">{event.timestamp.toLocaleTimeString()}</span>
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

<script lang="ts">
	import { formatToolEventLine, type ToolExecution } from '$lib/tools'
	import BaseToolCard from './BaseToolCard.svelte'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()
</script>

<BaseToolCard {execution} {compact} expandable>
	{#snippet body()}
		{#if execution.events.length > 0}
			<div class="mb-3">
				<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
					timeline
				</h4>
				<div class="space-y-1">
					{#each execution.events as event (event.id)}
						<div class="flex items-start gap-2 text-xs">
							<span class="text-white/30">{event.timestamp.toLocaleTimeString()}</span
							>
							<span class="text-white/60">{formatToolEventLine(event)}</span>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		{#if execution.events.length === 0 && Object.keys(execution.toolCall.arguments).length > 0}
			<div class="mb-3">
				<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
					arguments
				</h4>
				<pre
					class="rounded-pill overflow-x-auto bg-black/20 p-2 text-xs text-white/70">{JSON.stringify(
						execution.toolCall.arguments,
						null,
						2
					)}</pre>
			</div>
		{/if}

		{#if execution.events.length === 0 && execution.result}
			<div>
				<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
					result
				</h4>
				<pre
					class="rounded-pill max-h-32 overflow-auto bg-black/20 p-2 text-xs {execution
						.result.isError
						? 'text-red-300'
						: 'text-white/70'}">{execution.result.output}</pre>
			</div>
		{/if}

		{#if execution.error && !execution.result}
			<div>
				<h4 class="mb-1 text-xs font-medium tracking-wide text-red-400 uppercase">error</h4>
				<p class="text-sm text-red-300">{execution.error}</p>
			</div>
		{/if}
	{/snippet}
</BaseToolCard>

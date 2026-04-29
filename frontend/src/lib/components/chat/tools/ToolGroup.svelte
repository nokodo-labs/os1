<script lang="ts">
	import type { ToolExecution } from '$lib/tools'
	import MemoryCreateGroup from './MemoryCreateGroup.svelte'
	import ToolStep from './ToolStep.svelte'

	interface Props {
		executions: ToolExecution[]
	}

	let { executions }: Props = $props()

	// collapse consecutive memory_create steps into grouped segments
	type Segment =
		| { type: 'single'; execution: ToolExecution }
		| { type: 'memory_create_group'; executions: ToolExecution[] }

	let segments = $derived.by(() => {
		const result: Segment[] = []
		for (const exec of executions) {
			if (exec.toolCall.name === 'memory_create') {
				const last = result.at(-1)
				if (last?.type === 'memory_create_group') {
					last.executions.push(exec)
				} else {
					result.push({ type: 'memory_create_group', executions: [exec] })
				}
			} else {
				result.push({ type: 'single', execution: exec })
			}
		}
		return result
	})
</script>

<div class="tool-group">
	{#each segments as segment, i (segment.type === 'single' ? segment.execution.toolCall.id : `memory-group-${i}`)}
		<div class="tool-step-wrapper">
			{#if segment.type === 'memory_create_group'}
				{#if segment.executions.length === 1}
					<ToolStep execution={segment.executions[0]} />
				{:else}
					<MemoryCreateGroup executions={segment.executions} />
				{/if}
			{:else}
				<ToolStep execution={segment.execution} />
			{/if}
		</div>
	{/each}
</div>

<style>
	.tool-group {
		display: flex;
		flex-direction: column;
		padding: 2px 0;
	}

	.tool-step-wrapper {
		position: relative;
		padding-bottom: 4px;
	}

	.tool-step-wrapper:last-child {
		padding-bottom: 0;
	}

	.tool-step-wrapper:not(:last-child)::before {
		content: '';
		position: absolute;
		left: 12px;
		top: 24px;
		bottom: -8px;
		width: 1px;
		background-color: color-mix(in srgb, var(--color-foreground) 18%, transparent);
	}
</style>

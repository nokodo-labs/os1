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

	/* full-height vertical connector line with gap around each icon */
	.tool-step-wrapper::before {
		content: '';
		position: absolute;
		left: 12px;
		top: 0;
		bottom: 0;
		width: 1px;
		background-color: color-mix(in srgb, var(--color-foreground) 18%, transparent);
		-webkit-mask-image: linear-gradient(
			to bottom,
			#000 0 5px,
			transparent 5px 25px,
			#000 25px 100%
		);
		mask-image: linear-gradient(to bottom, #000 0 5px, transparent 5px 25px, #000 25px 100%);
	}

	/* first item: line starts below icon only */
	.tool-step-wrapper:first-child::before {
		-webkit-mask-image: linear-gradient(to bottom, transparent 0 25px, #000 25px 100%);
		mask-image: linear-gradient(to bottom, transparent 0 25px, #000 25px 100%);
	}

	/* last item: line ends above icon only */
	.tool-step-wrapper:last-child::before {
		-webkit-mask-image: linear-gradient(to bottom, #000 0 5px, transparent 5px 100%);
		mask-image: linear-gradient(to bottom, #000 0 5px, transparent 5px 100%);
	}

	/* single item: no line */
	.tool-step-wrapper:only-child::before {
		background: none;
		-webkit-mask-image: none;
		mask-image: none;
	}
</style>

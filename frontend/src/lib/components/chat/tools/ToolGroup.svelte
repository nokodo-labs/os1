<script lang="ts">
	import type { ToolExecution } from '$lib/tools'
	import ToolStep from './ToolStep.svelte'

	interface Props {
		executions: ToolExecution[]
	}

	let { executions }: Props = $props()

	let isSingle = $derived(executions.length === 1)
</script>

<div class="tool-group" class:single={isSingle}>
	{#each executions as execution, idx (execution.toolCall.id)}
		<div
			class="tool-step-wrapper"
			class:first={idx === 0}
			class:last={idx === executions.length - 1}
			class:only={isSingle}
		>
			<ToolStep {execution} />
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
	}

	/* vertical connector line via ::before */
	.tool-group:not(.single) .tool-step-wrapper::before {
		content: '';
		position: absolute;
		left: 12px;
		top: 0;
		bottom: 0;
		width: 1px;
		background-color: color-mix(in srgb, var(--color-foreground) 12%, transparent);
		/* gap around the icon (icon center at ~12px from top, 24px tall) */
		-webkit-mask-image: linear-gradient(
			to bottom,
			#000 0 4px,
			transparent 4px 28px,
			#000 28px 100%
		);
		mask-image: linear-gradient(to bottom, #000 0 4px, transparent 4px 28px, #000 28px 100%);
	}

	/* first item: line starts below icon */
	.tool-group:not(.single) .tool-step-wrapper.first::before {
		-webkit-mask-image: linear-gradient(to bottom, transparent 0 28px, #000 28px 100%);
		mask-image: linear-gradient(to bottom, transparent 0 28px, #000 28px 100%);
	}

	/* last item: line ends above icon */
	.tool-group:not(.single) .tool-step-wrapper.last::before {
		-webkit-mask-image: linear-gradient(to bottom, #000 0 4px, transparent 4px 100%);
		mask-image: linear-gradient(to bottom, #000 0 4px, transparent 4px 100%);
	}

	/* single item: no line */
	.tool-step-wrapper.only::before {
		display: none;
	}
</style>

<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import type { ToolExecution } from '$lib/tools'
	import { fade } from 'svelte/transition'

	interface Props {
		executions: ToolExecution[]
	}

	let { executions }: Props = $props()

	let allDone = $derived(executions.every((e) => e.status === 'completed'))
	let anyFailed = $derived(executions.some((e) => e.status === 'error'))
	let isActive = $derived(
		!allDone &&
			!anyFailed &&
			executions.some((e) => e.status === 'pending' || e.status === 'running')
	)
	let count = $derived(executions.length)

	let title = $derived.by(() => {
		if (anyFailed) return 'could not save memories'
		if (isActive) return `creating ${count} memories`
		return `created ${count} memories`
	})
</script>

<div class="flex items-start gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<div class="relative mt-px flex h-5 w-6 shrink-0 items-center justify-center">
		<Brain class="h-4.5 w-4.5 {anyFailed ? 'text-destructive' : 'text-foreground/80'}" />
	</div>

	<div class="min-w-0 flex-1">
		<div class="flex items-center gap-1.5 text-sm">
			{#if isActive}
				<ShimmerText className="text-foreground/90">{title}</ShimmerText>
			{:else}
				<span class="text-foreground/70">{title}</span>
			{/if}
		</div>
	</div>
</div>

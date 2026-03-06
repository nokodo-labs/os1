<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import { type ToolExecution } from '$lib/tools'
	import { onDestroy } from 'svelte'
	import { fade } from 'svelte/transition'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()

	// live timer for running state
	let elapsed = $state(0)
	let timerInterval: ReturnType<typeof setInterval> | null = null

	$effect(() => {
		if (
			(execution.status === 'pending' || execution.status === 'running') &&
			execution.startedAt
		) {
			// start the live timer
			const start = execution.startedAt.getTime()
			elapsed = (Date.now() - start) / 1000
			timerInterval = setInterval(() => {
				elapsed = (Date.now() - start) / 1000
			}, 100)
		} else {
			// stop the timer
			if (timerInterval) {
				clearInterval(timerInterval)
				timerInterval = null
			}
		}

		return () => {
			if (timerInterval) clearInterval(timerInterval)
		}
	})

	onDestroy(() => {
		if (timerInterval) clearInterval(timerInterval)
	})

	/** parse the actual elapsed time from the tool's JSON response */
	let serverElapsed = $derived.by(() => {
		if (!execution.result || execution.result.isError) return null
		try {
			const parsed = JSON.parse(execution.result.output)
			if (typeof parsed.elapsed_seconds === 'number') {
				return parsed.elapsed_seconds.toFixed(1)
			}
		} catch {
			// not json, ignore
		}
		return null
	})

	let isActive = $derived(execution.status === 'pending' || execution.status === 'running')
	let isError = $derived(execution.status === 'error')
	let isDone = $derived(execution.status === 'completed')

	/** use server elapsed when available, otherwise optimistic */
	let displayElapsed = $derived(serverElapsed ?? elapsed.toFixed(1))
</script>

{#if compact}
	<span
		class="inline-flex items-center gap-1.5 text-xs text-foreground/60"
		in:fade={{ duration: 150 }}
	>
		<Brain class="h-3.5 w-3.5" />
		{#if isActive}
			<ShimmerText>thinking</ShimmerText>
			<span class="text-foreground/50 tabular-nums">{elapsed.toFixed(1)}s</span>
		{:else if isDone}
			<span>thought for {displayElapsed}s</span>
			<Check class="h-3 w-3 text-green-400" />
		{:else if isError}
			<span class="text-red-400">thinking failed</span>
		{/if}
	</span>
{:else}
	<div class="flex items-center gap-2.5 py-1.5" in:fade={{ duration: 150 }}>
		<div
			class="relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full {isError
				? 'bg-red-500/15'
				: isDone
					? 'bg-foreground/6'
					: 'bg-foreground/6'}"
		>
			<Brain
				class="h-4 w-4 {isError
					? 'text-red-400'
					: isDone
						? 'text-foreground/70'
						: 'text-foreground/60'}"
			/>
			{#if isDone}
				<div
					class="absolute -right-0.5 -bottom-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full bg-green-500/90"
					in:fade={{ duration: 150 }}
				>
					<Check class="h-2.5 w-2.5 text-foreground" strokeWidth="3" />
				</div>
			{/if}
		</div>

		<div class="flex items-center gap-2 text-sm">
			{#if isActive}
				<ShimmerText className="text-foreground/70">thinking</ShimmerText>
				<span class="text-xs text-foreground/50 tabular-nums">{elapsed.toFixed(1)}s</span>
			{:else if isDone}
				<span class="text-foreground/50">thought for {displayElapsed}s</span>
			{:else if isError}
				<span class="text-red-400">thinking failed</span>
			{/if}
		</div>
	</div>
{/if}

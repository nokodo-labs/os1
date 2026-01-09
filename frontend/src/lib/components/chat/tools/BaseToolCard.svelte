<script lang="ts">
	import { type ToolExecution, getToolStatusLabel, getToolSummary } from '$lib/tools'
	import type { Snippet } from 'svelte'
	import { fade } from 'svelte/transition'

	interface Props {
		execution: ToolExecution
		compact?: boolean
		icon?: Snippet
		body?: Snippet
		expandable?: boolean
	}

	let { execution, compact = false, icon, body, expandable = false }: Props = $props()

	let isExpanded = $state(false)

	const statusColors: Record<string, string> = {
		pending: 'bg-white/10 text-white/60',
		running: 'bg-blue-500/20 text-blue-300',
		completed: 'bg-green-500/20 text-green-300',
		error: 'bg-red-500/20 text-red-300',
	}

	const statusIcons: Record<string, string> = {
		pending: '○',
		running: '◐',
		completed: '●',
		error: '✕',
	}

	let summary = $derived(getToolSummary(execution))
	let statusLabel = $derived(getToolStatusLabel(execution.status))
	let statusColor = $derived(statusColors[execution.status])
	let statusIcon = $derived(statusIcons[execution.status])
	let progressPercent = $derived(
		execution.progress !== undefined ? Math.round(execution.progress * 100) : null
	)

	function toggleExpand() {
		if (expandable) isExpanded = !isExpanded
	}
</script>

{#if compact}
	<span class="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs {statusColor}">
		<span class="animate-pulse" class:animate-none={execution.status !== 'running'}>
			{statusIcon}
		</span>
		<span>{summary.title}</span>
		{#if progressPercent !== null && execution.status === 'running'}
			<span class="text-white/40">{progressPercent}%</span>
		{/if}
	</span>
{:else}
	<div
		class="overflow-hidden rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm"
		in:fade={{ duration: 150 }}
	>
		{#if expandable}
			<button
				type="button"
				class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/5"
				onclick={toggleExpand}
			>
				<div
					class="flex h-8 w-8 items-center justify-center rounded-lg text-sm {statusColor}"
				>
					{#if icon}
						{@render icon()}
					{:else}
						<span
							class="text-lg"
							class:animate-spin={execution.status === 'running'}
							style={execution.status === 'running'
								? 'animation-duration: 2s'
								: undefined}
						>
							{statusIcon}
						</span>
					{/if}
				</div>

				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2">
						<span class="font-medium text-white/90">{summary.title}</span>
					</div>
					{#if summary.subtitle}
						<p class="truncate text-sm text-white/50">{summary.subtitle}</p>
					{/if}
				</div>

				<div class="flex items-center gap-2">
					{#if progressPercent !== null && execution.status === 'running'}
						<div class="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
							<div
								class="h-full bg-blue-400 transition-all duration-300"
								style="width: {progressPercent}%"
							></div>
						</div>
					{/if}
					<span class="text-xs text-white/40">{statusLabel}</span>
					<span
						class="text-white/40 transition-transform duration-200"
						class:rotate-180={isExpanded}
					>
						▾
					</span>
				</div>
			</button>
		{:else}
			<div class="flex w-full items-center gap-3 px-4 py-3 text-left">
				<div
					class="flex h-8 w-8 items-center justify-center rounded-lg text-sm {statusColor}"
				>
					{#if icon}
						{@render icon()}
					{:else}
						<span
							class="text-lg"
							class:animate-spin={execution.status === 'running'}
							style={execution.status === 'running'
								? 'animation-duration: 2s'
								: undefined}
						>
							{statusIcon}
						</span>
					{/if}
				</div>

				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2">
						<span class="font-medium text-white/90">{summary.title}</span>
					</div>
					{#if summary.subtitle}
						<p class="truncate text-sm text-white/50">{summary.subtitle}</p>
					{/if}
				</div>

				<div class="flex items-center gap-2">
					{#if progressPercent !== null && execution.status === 'running'}
						<div class="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
							<div
								class="h-full bg-blue-400 transition-all duration-300"
								style="width: {progressPercent}%"
							></div>
						</div>
					{/if}
					<span class="text-xs text-white/40">{statusLabel}</span>
				</div>
			</div>
		{/if}

		{#if body && (!expandable || isExpanded)}
			<div class="border-t border-white/10 px-4 py-3" in:fade={{ duration: 100 }}>
				{@render body()}
			</div>
		{/if}
	</div>
{/if}

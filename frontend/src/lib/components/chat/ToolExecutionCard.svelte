<script lang="ts">
	import AppNotification from '$lib/components/icons/AppNotification.svelte'
	import {
		type ToolExecution,
		formatToolEventLine,
		getToolStatusLabel,
		getToolSummary,
		isNativeTool,
	} from '$lib/tools'
	import { fade } from 'svelte/transition'

	interface Props {
		execution: ToolExecution
		compact?: boolean
	}

	let { execution, compact = false }: Props = $props()

	let isExpanded = $state(false)

	const statusColors = {
		pending: 'bg-white/10 text-white/60',
		running: 'bg-blue-500/20 text-blue-300',
		completed: 'bg-green-500/20 text-green-300',
		error: 'bg-red-500/20 text-red-300',
	}

	const statusIcons = {
		pending: '○',
		running: '◐',
		completed: '●',
		error: '✕',
	}

	let summary = $derived(getToolSummary(execution))
	let statusLabel = $derived(getToolStatusLabel(execution.status))
	let statusColor = $derived(statusColors[execution.status])
	let statusIcon = $derived(statusIcons[execution.status])
	let hasNativeUI = $derived(isNativeTool(execution.toolCall.name))
	let isNotificationTool = $derived(execution.toolCall.name === 'send_notification')
	let progressPercent = $derived(
		execution.progress !== undefined ? Math.round(execution.progress * 100) : null
	)

	let notificationPreview = $derived(
		(() => {
			if (execution.toolCall.name !== 'send_notification') return null
			const title =
				typeof execution.toolCall.arguments.title === 'string'
					? execution.toolCall.arguments.title
					: null
			const body =
				typeof execution.toolCall.arguments.body === 'string'
					? execution.toolCall.arguments.body
					: null
			if (!title || !body) return null
			return { title, body }
		})()
	)

	function toggleExpand() {
		isExpanded = !isExpanded
	}
</script>

{#if compact}
	<!-- Compact inline display -->
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
	<!-- Full card display -->
	<div
		class="overflow-hidden rounded-xl border border-white/10 bg-white/5 backdrop-blur-sm"
		in:fade={{ duration: 150 }}
	>
		<!-- Header -->
		{#if hasNativeUI}
			<div class="flex w-full items-center gap-3 px-4 py-3 text-left">
				<!-- Status indicator -->
				<div
					class="flex h-8 w-8 items-center justify-center rounded-lg text-sm {statusColor}"
				>
					{#if isNotificationTool}
						<AppNotification
							className={`h-4 w-4 text-white/80 ${execution.status === 'running' ? 'animate-pulse' : ''}`}
						/>
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

				<!-- Tool info -->
				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2">
						<span class="font-medium text-white/90">{summary.title}</span>
					</div>
					{#if summary.subtitle}
						<p class="truncate text-sm text-white/50">{summary.subtitle}</p>
					{/if}
				</div>

				<!-- Status badge -->
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
		{:else}
			<button
				type="button"
				class="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/5"
				onclick={toggleExpand}
			>
				<!-- Status indicator -->
				<div
					class="flex h-8 w-8 items-center justify-center rounded-lg text-sm {statusColor}"
				>
					{#if isNotificationTool}
						<AppNotification
							className={`h-4 w-4 text-white/80 ${execution.status === 'running' ? 'animate-pulse' : ''}`}
						/>
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

				<!-- Tool info -->
				<div class="min-w-0 flex-1">
					<div class="flex items-center gap-2">
						<span class="font-medium text-white/90">{summary.title}</span>
					</div>
					{#if summary.subtitle}
						<p class="truncate text-sm text-white/50">{summary.subtitle}</p>
					{/if}
				</div>

				<!-- Status badge -->
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
		{/if}

		<!-- Native tool body (never show JSON) -->
		{#if hasNativeUI}
			<div class="border-t border-white/10 px-4 py-3">
				{#if execution.toolCall.name === 'send_notification' && notificationPreview}
					<div class="rounded-lg border border-white/10 bg-white/5 p-3">
						<div class="text-sm font-semibold text-white/90">
							{notificationPreview.title}
						</div>
						<div class="mt-1 text-sm text-white/60">{notificationPreview.body}</div>
					</div>
				{/if}

				{#if execution.events.length > 0}
					<div class="mt-3 space-y-1">
						{#each execution.events as event (event.id)}
							<div class="flex items-start gap-2 text-xs text-white/60">
								<span class="text-white/30">
									{event.timestamp.toLocaleTimeString()}
								</span>
								<span>{formatToolEventLine(event)}</span>
							</div>
						{/each}
					</div>
				{/if}

				{#if execution.status === 'error' && execution.error}
					<div class="mt-3 text-sm text-red-300">{execution.error}</div>
				{/if}
			</div>
		{/if}

		<!-- Expanded content (non-native only) -->
		{#if isExpanded && !hasNativeUI}
			<div class="border-t border-white/10 px-4 py-3" in:fade={{ duration: 100 }}>
				<!-- Events timeline (drives UX when present) -->
				{#if execution.events.length > 0}
					<div class="mb-3">
						<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
							timeline
						</h4>
						<div class="space-y-1">
							{#each execution.events as event (event.id)}
								<div class="flex items-start gap-2 text-xs">
									<span class="text-white/30">
										{event.timestamp.toLocaleTimeString()}
									</span>
									<span class="text-white/60">{formatToolEventLine(event)}</span>
								</div>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Fallback internals (only if no events) -->
				{#if execution.events.length === 0 && Object.keys(execution.toolCall.arguments).length > 0}
					<div class="mb-3">
						<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
							arguments
						</h4>
						<pre
							class="overflow-x-auto rounded-lg bg-black/20 p-2 text-xs text-white/70">{JSON.stringify(
								execution.toolCall.arguments,
								null,
								2
							)}</pre>
					</div>
				{/if}

				<!-- Result (only if no events) -->
				{#if execution.events.length === 0 && execution.result}
					<div>
						<h4 class="mb-1 text-xs font-medium tracking-wide text-white/40 uppercase">
							result
						</h4>
						<pre
							class="max-h-32 overflow-auto rounded-lg bg-black/20 p-2 text-xs {execution
								.result.isError
								? 'text-red-300'
								: 'text-white/70'}">{execution.result.output}</pre>
					</div>
				{/if}

				<!-- Error -->
				{#if execution.error && !execution.result}
					<div>
						<h4 class="mb-1 text-xs font-medium tracking-wide text-red-400 uppercase">
							error
						</h4>
						<p class="text-sm text-red-300">{execution.error}</p>
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}

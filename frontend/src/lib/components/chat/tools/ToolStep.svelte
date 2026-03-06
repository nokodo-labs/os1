<script lang="ts">
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import Bell from '$lib/components/icons/Bell.svelte'
	import Brain from '$lib/components/icons/Brain.svelte'
	import Check from '$lib/components/icons/Check.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import CommandLine from '$lib/components/icons/CommandLine.svelte'
	import Document from '$lib/components/icons/Document.svelte'
	import Eye from '$lib/components/icons/Eye.svelte'
	import GlobeAlt from '$lib/components/icons/GlobeAlt.svelte'
	import Note from '$lib/components/icons/Note.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import Photo from '$lib/components/icons/Photo.svelte'
	import Sparkles from '$lib/components/icons/Sparkles.svelte'
	import { getThinkElapsed, getToolSummary, type ToolExecution } from '$lib/tools'
	import { onDestroy } from 'svelte'
	import { fade } from 'svelte/transition'
	import MemoryRecallBody from './steps/MemoryRecallBody.svelte'
	import WebSearchBody from './steps/WebSearchBody.svelte'

	interface Props {
		execution: ToolExecution
	}

	let { execution }: Props = $props()

	let name = $derived(execution.toolCall.name)
	let isActive = $derived(execution.status === 'pending' || execution.status === 'running')
	let isFailed = $derived(execution.status === 'error')
	let isDone = $derived(execution.status === 'completed')
	let summary = $derived(getToolSummary(execution))

	// think tool timer
	let elapsed = $state(0)
	let timerInterval: ReturnType<typeof setInterval> | null = null

	$effect(() => {
		if (name === 'think' && isActive && execution.startedAt) {
			const start = execution.startedAt.getTime()
			elapsed = (Date.now() - start) / 1000
			timerInterval = setInterval(() => {
				elapsed = (Date.now() - start) / 1000
			}, 100)
		} else {
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

	let thinkDisplay = $derived.by(() => {
		if (name !== 'think') return null
		if (isActive) return elapsed.toFixed(1)
		const server = getThinkElapsed(execution)
		return server ?? null
	})

	// collapsible body
	let hasBody = $derived(
		name === 'agentic_web_search' || name === 'memory_recall' || name === 'code_interpreter'
	)
	let isExpanded = $state(true)

	function toggleExpand() {
		if (hasBody) isExpanded = !isExpanded
	}
</script>

<div class="flex items-start gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<!-- icon column - vertically centered with title row -->
	<div class="relative mt-px flex h-5 w-6 shrink-0 items-center justify-center">
		{#if name === 'think'}
			<Brain class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'agentic_web_search' || name === 'fetch_url'}
			<GlobeAlt class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'memory_recall' || name === 'memory_create'}
			<Brain class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'note_get' || name === 'note_write'}
			<Note class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'reminder_get' || name === 'reminder_write'}
			<Bell class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'file_get'}
			<Document class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'file_edit'}
			<Pencil class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'generate_image'}
			<Photo class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'code_interpreter'}
			<CommandLine class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'send_notification'}
			<Bell class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else if name === 'reveal_attachment'}
			<Eye class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{:else}
			<Sparkles class="h-4.5 w-4.5 {isFailed ? 'text-red-400' : 'text-foreground/80'}" />
		{/if}

		<!-- completion badge -->
		{#if isDone}
			<div
				class="absolute -right-0.5 -bottom-0.5 flex h-3 w-3 items-center justify-center rounded-full bg-green-500/90"
				in:fade={{ duration: 120 }}
			>
				<Check class="h-2 w-2 text-white" strokeWidth="3" />
			</div>
		{/if}
	</div>

	<!-- text column -->
	<div class="min-w-0 flex-1">
		<!-- title row -->
		{#if hasBody}
			<button
				type="button"
				class="hover:text-foreground flex items-center gap-1.5 text-left text-sm transition-colors"
				onclick={toggleExpand}
			>
				{#if isActive}
					<ShimmerText className="text-foreground/90">{summary.title}</ShimmerText>
				{:else}
					<span class="text-foreground/70">{summary.title}</span>
				{/if}
				{#if summary.subtitle}
					<span class="text-foreground/40 max-w-48 truncate text-xs"
						>"{summary.subtitle}"</span
					>
				{/if}
				{#if name === 'think' && thinkDisplay}
					<span class="text-foreground/50 text-xs tabular-nums">{thinkDisplay}s</span>
				{/if}
				<ChevronRight
					class="text-foreground/40 h-3 w-3 transition-transform duration-150 {isExpanded
						? 'rotate-90'
						: ''}"
				/>
			</button>
		{:else}
			<div class="flex items-center gap-1.5 text-sm">
				{#if isActive}
					<ShimmerText className="text-foreground/90">{summary.title}</ShimmerText>
				{:else}
					<span class="text-foreground/70">{summary.title}</span>
				{/if}
				{#if summary.subtitle}
					<span class="text-foreground/40 max-w-48 truncate text-xs"
						>"{summary.subtitle}"</span
					>
				{/if}
				{#if name === 'think' && thinkDisplay}
					<span class="text-foreground/50 text-xs tabular-nums">{thinkDisplay}s</span>
				{/if}
			</div>
		{/if}

		<!-- collapsible body -->
		{#if hasBody && isExpanded}
			<div class="mt-1.5 mb-1" in:fade={{ duration: 100 }}>
				{#if name === 'agentic_web_search'}
					<WebSearchBody {execution} />
				{:else if name === 'memory_recall'}
					<MemoryRecallBody {execution} />
				{:else if name === 'code_interpreter'}
					<!-- code output -->
					{#if execution.result}
						<pre
							class="bg-foreground/5 text-foreground/60 max-h-32 overflow-auto rounded-lg p-2.5 text-xs {execution
								.result.isError
								? 'text-red-300'
								: ''}">{execution.result.output}</pre>
					{/if}
				{/if}
			</div>
		{/if}
	</div>
</div>

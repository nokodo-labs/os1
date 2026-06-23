<script lang="ts">
	/** renders one compact tool execution row in the chat timeline. */

	import { getApiBaseUrl } from '$lib/api/client'
	import { extractFileParts, extractMediaParts, hasAttachmentParts } from '$lib/chat/helpers'
	import AttachmentRefs from '$lib/components/chat/AttachmentRefs.svelte'
	import MediaAttachments from '$lib/components/chat/MediaAttachments.svelte'
	import ShimmerText from '$lib/components/effects/ShimmerText.svelte'
	import ChevronRight from '$lib/components/icons/ChevronRight.svelte'
	import Component from '$lib/components/icons/Component.svelte'
	import { getThinkElapsed, getToolSummary, isResolverTool, type ToolExecution } from '$lib/tools'
	import { parseJsonRecord, readRecordArray, readRecordField } from '$lib/utils/records'
	import { onDestroy } from 'svelte'
	import { fade } from 'svelte/transition'
	import CalendarEventBody from './steps/CalendarEventBody.svelte'
	import CodeInterpreterBody from './steps/CodeInterpreterBody.svelte'
	import FetchUrlBody from './steps/FetchUrlBody.svelte'
	import MemoryRecallBody from './steps/MemoryRecallBody.svelte'
	import ResourceBody from './steps/ResourceBody.svelte'
	import WebSearchBody from './steps/WebSearchBody.svelte'
	import ToolIcon from './ToolIcon.svelte'

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
	let calendarResultCount = $derived.by(() => {
		if (
			(name !== 'calendar_event_get' && name !== 'calendar_event_write') ||
			!execution.result ||
			execution.result.isError
		) {
			return 0
		}
		const output = parseJsonRecord(execution.result.output)
		return readRecordArray(output?.results).length + (readRecordField(output, 'event') ? 1 : 0)
	})
	let hasBody = $derived(
		name === 'agentic_web_search' ||
			calendarResultCount > 0 ||
			name === 'code_interpreter' ||
			name === 'fetch_url' ||
			(isDone && summary.resourceId != null)
	)
	let isExpanded = $state(false)
	let userToggled = $state(false)

	// auto-expand web search while running, auto-collapse when done
	$effect(() => {
		if (name !== 'agentic_web_search' || userToggled) return
		isExpanded = isActive
	})

	// tool result attachments (images/files from tool message)
	let resultAttachments = $derived(execution.result?.contentParts)
	// resolver tools (file readers) inject content that duplicates a resource
	// ref rendered at its origin, so their inline attachments are ignored.
	let hasResultAttachments = $derived(
		!isResolverTool(name) && resultAttachments != null && hasAttachmentParts(resultAttachments)
	)
	// resource refs attached by producer tools (generated media, etc.)
	let resultRefs = $derived(execution.result?.attachmentRefs ?? [])

	/** toggles the optional expanded body for tools with rich result content. */
	function toggleExpand() {
		if (hasBody) {
			userToggled = true
			isExpanded = !isExpanded
		}
	}

	/** removes wrapping quotes from compact subtitles without touching inner text. */
	function subtitleText(value: string): string {
		const trimmed = value.trim()
		const leftDoubleQuote = String.fromCharCode(0x201c)
		const rightDoubleQuote = String.fromCharCode(0x201d)
		const quotePairs: [string, string][] = [
			['"', '"'],
			["'", "'"],
			[leftDoubleQuote, rightDoubleQuote],
		]
		for (const [open, close] of quotePairs) {
			if (trimmed.startsWith(open) && trimmed.endsWith(close) && trimmed.length > 1) {
				return trimmed.slice(open.length, -close.length)
			}
		}
		return value
	}
</script>

<div class="flex items-start gap-2.5 py-1" in:fade={{ duration: 120 }}>
	<!-- icon column - vertically centered with title row -->
	<div class="relative mt-px flex h-5 w-6 shrink-0 items-center justify-center">
		<ToolIcon toolName={name} {isFailed} />
	</div>

	<!-- text column -->
	<div class="min-w-0 flex-1">
		<!-- title row -->
		{#if hasBody}
			<button
				type="button"
				class="hover:text-foreground flex min-w-0 cursor-pointer flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-left text-sm transition-colors"
				onclick={toggleExpand}
			>
				{#if isActive}
					<ShimmerText className="text-foreground/90">{summary.title}</ShimmerText>
				{:else}
					<span class="text-foreground/70">{summary.title}</span>
				{/if}
				{#if summary.subtitle}
					<span class="text-foreground/40 max-w-full min-w-0 text-xs wrap-break-word"
						>{subtitleText(summary.subtitle)}</span
					>
				{/if}
				{#if name === 'think' && thinkDisplay && summary.title !== `thought for ${thinkDisplay}s`}
					<span class="text-foreground/50 text-xs tabular-nums">{thinkDisplay}s</span>
				{/if}
				{#if summary.mcpServerName}
					<span
						class="bg-foreground/8 text-foreground/55 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px]"
					>
						<Component class="h-3 w-3 shrink-0" />
						{summary.mcpServerName}
					</span>
				{/if}
				<ChevronRight
					class="text-foreground/40 h-3 w-3 transition-transform duration-150 {isExpanded
						? 'rotate-90'
						: ''}"
				/>
			</button>
		{:else}
			<div class="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-sm">
				{#if isActive}
					<ShimmerText className="text-foreground/90">{summary.title}</ShimmerText>
				{:else}
					<span class="text-foreground/70">{summary.title}</span>
				{/if}
				{#if summary.subtitle}
					<span class="text-foreground/40 max-w-full min-w-0 text-xs wrap-break-word"
						>{subtitleText(summary.subtitle)}</span
					>
				{/if}
				{#if name === 'think' && thinkDisplay && summary.title !== `thought for ${thinkDisplay}s`}
					<span class="text-foreground/50 text-xs tabular-nums">{thinkDisplay}s</span>
				{/if}
				{#if summary.mcpServerName}
					<span
						class="bg-foreground/8 text-foreground/55 inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px]"
					>
						<Component class="h-3 w-3 shrink-0" />
						{summary.mcpServerName}
					</span>
				{/if}
			</div>
		{/if}

		<!-- collapsible body -->
		{#if hasBody && isExpanded}
			<div class="mt-1.5 mb-1" in:fade={{ duration: 100 }}>
				{#if name === 'agentic_web_search'}
					<WebSearchBody {execution} />
				{:else if name === 'fetch_url'}
					<FetchUrlBody {execution} />
				{:else if name === 'memory_recall'}
					<MemoryRecallBody {execution} />
				{:else if calendarResultCount > 0 && (name === 'calendar_event_get' || name === 'calendar_event_write')}
					<CalendarEventBody {execution} />
				{:else if name === 'code_interpreter'}
					<CodeInterpreterBody {execution} />
				{:else if summary.resourceId && summary.resourceType}
					<ResourceBody
						{execution}
						resourceType={summary.resourceType}
						resourceId={summary.resourceId}
					/>
				{/if}
			</div>
		{/if}

		<!-- tool result attachments (images, files) -->
		{#if hasResultAttachments && resultAttachments}
			<div class="mt-2">
				<MediaAttachments
					mediaParts={extractMediaParts(resultAttachments, getApiBaseUrl())}
					fileParts={extractFileParts(resultAttachments, getApiBaseUrl())}
				/>
			</div>
		{/if}

		<!-- tool result resource refs (producer tools: generated media, etc.) -->
		{#if resultRefs.length > 0}
			<div class="mt-2">
				<AttachmentRefs refs={resultRefs} />
			</div>
		{/if}
	</div>
</div>

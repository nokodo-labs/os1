<script lang="ts">
	import { page } from '$app/state'
	import { eventStreamClient, runChatStream, type StreamEvent } from '$lib/api/streaming'
	import type { components } from '$lib/api/types'
	import { v1Client } from '$lib/api/v1/client'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import Button from '$lib/components/chat/Button.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import ToolExecutionCard from '$lib/components/chat/ToolExecutionCard.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import NokodoLoader from '$lib/components/common/NokodoLoader.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import { useSystemChrome } from '$lib/contexts/systemChromeContext.svelte'
	import { agentsList, loadAgents } from '$lib/stores/agents'
	import {
		consumePendingChatStart,
		currentUser,
		pendingChatStart,
		setActiveThread,
		type Thread,
	} from '$lib/stores/session'
	import {
		ToolExecutionTracker,
		parseToolCalls,
		parseToolEvent,
		parseToolResult,
		type ToolCall,
	} from '$lib/tools'
	import { tick } from 'svelte'
	import { SvelteMap, SvelteSet } from 'svelte/reactivity'
	import { fade } from 'svelte/transition'

	type ApiMessage = components['schemas']['Message']
	type ApiEvent = components['schemas']['Event']

	type RunItem =
		| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
		| { kind: 'assistant'; message: ApiMessage }
		| { kind: 'tool'; toolCallId: string }
		| { kind: 'streaming_assistant' }
		| { kind: 'streaming_tool'; toolCallId: string }

	interface RunBlock {
		runId: string
		title: string
		startedAt: Date
		items: RunItem[]
	}

	interface StreamingAssistantState {
		runId: string | null
		messageId: string
		content: string
		timestamp: Date
		senderAgentId: string | null
		toolCalls: ToolCall[]
	}

	let messages = $state<ApiMessage[]>([])
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let selectedAgent = $state('')
	let didLoadAgents = $state(false)
	let optimisticUserMessage = $state<{ content: string; timestamp: Date } | null>(null)
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let runError = $state(false)
	let lastRunInput = $state('')
	let runBlocks = $state<RunBlock[]>([])

	let scrollContainer = $state<HTMLElement | null>(null)
	let inputOverlay = $state<HTMLElement | null>(null)
	let autoScroll = $state(true)
	let initialScrollDone = $state(false)
	let lastThreadId = $state<string | null>(null)
	let inputOverlayHeight = $state(0)
	let scrollQueued = false
	const AUTO_SCROLL_BUFFER_PX = 50

	function computeIsAtBottom(element: HTMLElement): boolean {
		return (
			element.scrollHeight - element.scrollTop <= element.clientHeight + AUTO_SCROLL_BUFFER_PX
		)
	}

	function handleScroll() {
		if (!scrollContainer) return
		const atBottom = computeIsAtBottom(scrollContainer)
		if (atBottom !== autoScroll) autoScroll = atBottom
	}

	function scrollToBottom(behavior: 'auto' | 'smooth' = 'auto') {
		if (!scrollContainer) return
		scrollContainer.scrollTo({ top: scrollContainer.scrollHeight, behavior })
	}

	async function queueScrollToBottom(behavior: 'auto' | 'smooth' = 'auto') {
		if (!scrollContainer) return
		if (scrollQueued) return
		scrollQueued = true
		await tick()
		requestAnimationFrame(() => {
			scrollQueued = false
			scrollToBottom(behavior)
		})
	}

	$effect(() => {
		if (!inputOverlay) {
			inputOverlayHeight = 0
			return
		}
		const update = () => {
			inputOverlayHeight = inputOverlay?.offsetHeight ?? 0
		}
		update()
		const ro = new ResizeObserver(update)
		ro.observe(inputOverlay)
		return () => ro.disconnect()
	})
	let toolTracker = $state(new ToolExecutionTracker())
	let toolTick = $state(0)

	const chrome = useSystemChrome()
	let selectedAgentName = $derived(
		$agentsList.find((a) => a.id === selectedAgent)?.name ?? 'assistant'
	)
	let agentNameById = $derived(new SvelteMap($agentsList.map((a) => [a.id, a.name])))
	let agentAvatarById = $derived(
		new SvelteMap($agentsList.map((a) => [a.id, a.profile_image_url ?? null]))
	)
	const currentUserId = $derived($currentUser?.id ?? null)

	let thread = $state<Thread | null>(null)
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)
	let showThreadLoader = $derived(isThreadLoading)

	function contentPartsToText(parts: ApiMessage['content']): string {
		if (!parts || parts.length === 0) return ''
		return parts
			.map((p) => {
				if (!p) return ''
				if (p.type === 'text') return p.text
				if (p.type === 'refusal') return p.reason
				if (p.type === 'json') {
					try {
						return JSON.stringify(p.data)
					} catch {
						return ''
					}
				}
				return ''
			})
			.filter(Boolean)
			.join('\n')
	}
	function getRunId(msg: Pick<ApiMessage, 'metadata_' | 'id'>): string {
		const runId =
			msg.metadata_ && typeof msg.metadata_.run_id === 'string' ? msg.metadata_.run_id : null
		return runId ?? `legacy-${msg.id}`
	}

	function getMessageCreatedAt(msg: ApiMessage): Date {
		return msg.created_at ? new Date(msg.created_at) : new Date(0)
	}

	function upsertToolCalls(existing: ToolCall[], incoming: unknown): ToolCall[] {
		const out = new SvelteMap(existing.map((tc) => [tc.id, tc]))
		if (!Array.isArray(incoming)) return Array.from(out.values())
		for (const item of incoming) {
			if (!item || typeof item !== 'object') continue
			const tc = item as Record<string, unknown>
			const id = typeof tc.id === 'string' ? tc.id : null
			const name = typeof tc.name === 'string' ? tc.name : null
			const args =
				tc.arguments && typeof tc.arguments === 'object' && tc.arguments !== null
					? (tc.arguments as Record<string, unknown>)
					: {}
			if (!id || !name) continue
			out.set(id, { id, name, arguments: args })
		}
		return Array.from(out.values())
	}

	function rebuildRunBlocks(): void {
		const sorted = messages.slice().sort((a, b) => {
			return getMessageCreatedAt(a).getTime() - getMessageCreatedAt(b).getTime()
		})

		const blocks: RunBlock[] = []
		const byRun = new SvelteMap<string, RunBlock>()
		const seenToolCalls = new SvelteMap<string, SvelteSet<string>>()

		const ensureBlock = (runId: string, startedAt: Date, title: string): RunBlock => {
			const existing = byRun.get(runId)
			if (existing) return existing
			const block: RunBlock = { runId, startedAt, title, items: [] }
			byRun.set(runId, block)
			blocks.push(block)
			return block
		}

		for (const msg of sorted) {
			const runId = getRunId(msg)
			const block = ensureBlock(runId, getMessageCreatedAt(msg), 'assistant')
			let seen = seenToolCalls.get(runId)
			if (!seen) {
				seen = new SvelteSet()
				seenToolCalls.set(runId, seen)
			}

			if (msg.type === 'user') {
				const align: 'left' | 'right' =
					currentUserId && msg.sender_user_id && msg.sender_user_id !== currentUserId
						? 'left'
						: 'right'
				block.items.push({ kind: 'user', message: msg, align })
				continue
			}

			if (msg.type === 'assistant') {
				for (const tc of parseToolCalls(msg)) {
					toolTracker.registerToolCall(tc)
					if (!seen.has(tc.id)) {
						seen.add(tc.id)
						block.items.push({ kind: 'tool', toolCallId: tc.id })
					}
				}
				const text = contentPartsToText(msg.content).trim()
				if (text.length > 0) block.items.push({ kind: 'assistant', message: msg })
				continue
			}

			if (msg.type === 'tool') {
				const result = parseToolResult(msg)
				if (result) toolTracker.registerResult(result)
				continue
			}
		}

		if (streamingAssistant) {
			const runId = streamingAssistant.runId ?? `legacy-${streamingAssistant.messageId}`
			const block = ensureBlock(runId, streamingAssistant.timestamp, 'assistant')
			let seen = seenToolCalls.get(runId)
			if (!seen) {
				seen = new SvelteSet()
				seenToolCalls.set(runId, seen)
			}
			block.items.push({ kind: 'streaming_assistant' })
			for (const tc of streamingAssistant.toolCalls) {
				toolTracker.registerToolCall(tc)
				if (!seen.has(tc.id)) {
					seen.add(tc.id)
					block.items.push({ kind: 'streaming_tool', toolCallId: tc.id })
				}
			}
		}

		runBlocks = blocks
	}

	function getBlockToolCallIds(block: RunBlock): string[] {
		return block.items
			.filter((item) => item.kind === 'tool' || item.kind === 'streaming_tool')
			.map((item) => item.toolCallId)
	}

	function getBlockLastAssistantMessage(block: RunBlock): ApiMessage | null {
		for (let i = block.items.length - 1; i >= 0; i--) {
			const item = block.items[i]
			if (item.kind === 'assistant') return item.message
		}
		return null
	}

	function blockHasStreamingAssistant(block: RunBlock): boolean {
		return block.items.some((item) => item.kind === 'streaming_assistant')
	}

	async function fetchToolEventsForThread(threadId: string, msgIds: string[]): Promise<void> {
		if (msgIds.length === 0) return
		const { data, error } = await v1Client().POST(
			'/threads/{thread_id}/events/by-message-ids',
			{
				params: { path: { thread_id: threadId } },
				body: { message_ids: msgIds },
			}
		)
		if (error || !data) return
		for (const ev of data as ApiEvent[]) {
			const toolEv = parseToolEvent({
				type: ev.type,
				data: (ev.data ?? {}) as Record<string, unknown>,
				created_at: ev.created_at ?? undefined,
				message_id: ev.message_id ?? undefined,
			})
			if (toolEv) toolTracker.processEvent(toolEv)
		}
		toolTick++
	}

	$effect(() => {
		if (didLoadAgents) return
		didLoadAgents = true
		void loadAgents()
	})

	$effect(() => {
		if (selectedAgent !== '') return
		if ($agentsList.length === 0) return
		selectedAgent = $agentsList[0].id
	})

	async function loadBranch(threadId: string): Promise<boolean> {
		const { data, error } = await v1Client().GET('/threads/{thread_id}/branch', {
			params: { path: { thread_id: threadId } },
		})
		if (error) {
			console.error('Failed to load thread branch', error)
			messages = []
			return false
		}
		toolTracker.clear()
		messages = (data ?? []) as ApiMessage[]
		for (const msg of messages) {
			if (msg.type === 'assistant') {
				for (const tc of parseToolCalls(msg)) toolTracker.registerToolCall(tc)
			}
			if (msg.type === 'tool') {
				const result = parseToolResult(msg)
				if (result) toolTracker.registerResult(result)
			}
		}
		await fetchToolEventsForThread(
			threadId,
			messages.filter((m) => m.type === 'assistant').map((m) => m.id)
		)
		rebuildRunBlocks()
		return true
	}

	$effect(() => {
		rebuildRunBlocks()
	})

	$effect(() => {
		if (!thread) return
		const threadId = thread.id
		const unsubscribe = eventStreamClient.subscribe((msg) => {
			if (!msg || typeof msg !== 'object') return
			const ev = msg as StreamEvent
			if (!ev.type || typeof ev.type !== 'string') return
			if (!ev.type.startsWith('tool.')) return
			if (ev.thread_id !== threadId) return
			const toolEv = parseToolEvent({
				type: ev.type,
				data: (ev.data ?? {}) as Record<string, unknown>,
				created_at: ev.created_at ?? undefined,
				message_id: ev.message_id ?? undefined,
			})
			if (!toolEv) return
			toolTracker.processEvent(toolEv)
			toolTick++
		})
		return unsubscribe
	})

	$effect(() => {
		const threadId = page.params.id
		if (!threadId) {
			thread = null
			setActiveThread(null)
			messages = []
			isThreadLoading = false
			hasLoadedBranch = false
			return
		}

		let cancelled = false
		isThreadLoading = true
		hasLoadedBranch = false
		void (async () => {
			try {
				const { data } = await v1Client().GET('/threads/{thread_id}', {
					params: { path: { thread_id: threadId } },
				})
				if (cancelled) return
				thread = data ?? null
				setActiveThread(data ?? null)
				if (data) {
					hasLoadedBranch = await loadBranch(data.id)
				} else {
					hasLoadedBranch = true
				}
			} finally {
				if (!cancelled) isThreadLoading = false
			}
		})()

		return () => {
			cancelled = true
			isThreadLoading = true
			thread = null
			setActiveThread(null)
			messages = []
			hasLoadedBranch = false
		}
	})

	$effect(() => {
		chrome.setAgentSelector({
			selectedAgent,
			onAgentChange: (agentId: string) => (selectedAgent = agentId),
		})
	})

	$effect(() => {
		return () => chrome.setAgentSelector(null)
	})

	$effect(() => {
		if (!thread) return
		const pending = $pendingChatStart
		if (!pending || pending.threadId !== thread.id) return
		if (messages.length !== 0) {
			consumePendingChatStart(thread.id)
			return
		}
		if (isGenerating || runError || optimisticUserMessage !== null || selectedAgent === '')
			return
		const content = consumePendingChatStart(thread.id)
		if (!content) return
		handleSendMessage(content)
	})

	async function handleSendMessage(content: string) {
		const trimmed = content.trim()
		if (!trimmed) return
		if (!thread) return
		const runBaseMessage = trimmed
		if (!selectedAgent) {
			runError = true
			lastRunInput = runBaseMessage
			optimisticUserMessage = { content: runBaseMessage, timestamp: new Date() }
			return
		}
		runError = false
		lastRunInput = runBaseMessage
		// optimistic user message will be replaced by message_created event
		optimisticUserMessage = { content: runBaseMessage, timestamp: new Date() }
		const shouldAutoScroll = scrollContainer ? computeIsAtBottom(scrollContainer) : true
		isGenerating = true
		streamingAssistant = {
			runId: null,
			messageId: `pending-${activeRun + 1}`,
			content: '',
			timestamp: new Date(),
			senderAgentId: selectedAgent,
			toolCalls: [],
		}
		const runId = ++activeRun
		rebuildRunBlocks()
		if (shouldAutoScroll) {
			autoScroll = true
			void queueScrollToBottom('smooth')
		}

		try {
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent,
				input: runBaseMessage,
				runId,
			})
			if (runId !== activeRun) return
			inputValue = ''
			runError = false
			// messages are added via message_created events during streaming
			optimisticUserMessage = null
			streamingAssistant = null
		} catch (e) {
			console.error('Failed to run thread', e)
			runError = true
			optimisticUserMessage = null
			streamingAssistant = null
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	$effect(() => {
		const threadId = page.params.id
		if (!threadId) return
		if (threadId !== lastThreadId) {
			lastThreadId = threadId
			initialScrollDone = false
			autoScroll = true
		}
		if (!hasLoadedBranch) {
			initialScrollDone = false
			return
		}
		if (!scrollContainer) return

		// Dependency reads
		const streamingContent = streamingAssistant?.content ?? ''
		const optimisticContent = optimisticUserMessage?.content ?? ''
		const blocksCount = runBlocks.length
		void streamingContent
		void optimisticContent
		void blocksCount
		void inputOverlayHeight

		if (!initialScrollDone) {
			initialScrollDone = true
			void queueScrollToBottom('auto')
			return
		}

		// Only keep pinned while the agent is streaming, and only if the user was already at bottom.
		if (isGenerating && autoScroll) void queueScrollToBottom('auto')
	})

	function sdkPartsToText(parts: unknown): string {
		if (!Array.isArray(parts)) return ''
		return parts
			.map((p) => {
				if (!p || typeof p !== 'object') return ''
				const part = p as Record<string, unknown>
				const type = typeof part.type === 'string' ? part.type : ''
				if (type === 'text' && typeof part.text === 'string') return part.text
				if (type === 'refusal' && typeof part.reason === 'string') return part.reason
				if (type === 'json' && part.data != null) {
					try {
						return JSON.stringify(part.data)
					} catch {
						return ''
					}
				}
				return ''
			})
			.filter(Boolean)
			.join('\n')
	}

	let runAbortController: AbortController | null = null

	async function runThreadStream(opts: {
		threadId: string
		agentId: string
		input: string | null
		runId: number
	}): Promise<void> {
		runAbortController?.abort()
		runAbortController = new AbortController()

		for await (const delta of runChatStream({
			threadId: opts.threadId,
			agentId: opts.agentId,
			input: opts.input,
			signal: runAbortController.signal,
		})) {
			if (opts.runId !== activeRun) {
				runAbortController.abort()
				return
			}

			switch (delta.event) {
				case 'error':
					throw new Error(delta.data.message || 'generation failed')
				case 'done':
					return
				case 'message_created': {
					const msg = delta.data as unknown as ApiMessage
					if (msg.type === 'user') optimisticUserMessage = null
					messages = [...messages, msg]
					rebuildRunBlocks()
					break
				}
				case 'delta': {
					const env = delta.data
					const d = env.delta as Record<string, unknown>
					const messageId = env.message_id

					// agent done sentinel
					if (d && d.done === true) return

					// tool results (register against tool_call_id)
					if (d && typeof d === 'object' && d.tool) {
						const tool = d.tool as Record<string, unknown>
						const toolCallId =
							typeof tool.tool_call_id === 'string' ? tool.tool_call_id : null
						const output = typeof tool.tool_output === 'string' ? tool.tool_output : ''
						const isError = tool.is_error === true
						if (toolCallId) {
							toolTracker.registerResult({ toolCallId, output, isError })
							toolTick++
						}
					}

					// assistant streaming
					if (d && typeof d === 'object' && d.chat && messageId) {
						const chat = d.chat as Record<string, unknown>
						const msg = (chat.message ?? null) as Record<string, unknown> | null
						const parts = msg ? msg.content : null
						const chunkText = sdkPartsToText(parts)
						const toolCalls = msg ? msg.tool_calls : null
						const isDone = chat.done === true

						if (!streamingAssistant || streamingAssistant.messageId !== messageId) {
							streamingAssistant = {
								runId: typeof env.run_id === 'string' ? env.run_id : null,
								messageId,
								content: '',
								timestamp: new Date(),
								senderAgentId: selectedAgent,
								toolCalls: [],
							}
						}

						if (chunkText) streamingAssistant.content += chunkText
						streamingAssistant.toolCalls = upsertToolCalls(
							streamingAssistant.toolCalls,
							toolCalls
						)
						for (const tc of streamingAssistant.toolCalls)
							toolTracker.registerToolCall(tc)
						toolTick++
						rebuildRunBlocks()

						if (isDone) {
							const content = streamingAssistant.content.trim()
							const finalized: ApiMessage = {
								id: streamingAssistant.messageId,
								thread_id: opts.threadId,
								parent_id: null,
								type: 'assistant',
								content: content ? [{ type: 'text', text: content }] : [],
								tool_calls: streamingAssistant.toolCalls.map((tc) => ({
									id: tc.id,
									name: tc.name,
									arguments: tc.arguments,
								})),
								metadata_: streamingAssistant.runId
									? { run_id: streamingAssistant.runId }
									: {},
								sender_agent_id: streamingAssistant.senderAgentId,
								sender_user_id: null,
								created_at: new Date().toISOString(),
							} as unknown as ApiMessage
							if (!messages.some((m) => m.id === finalized.id)) {
								messages = [...messages, finalized]
							}
							streamingAssistant = null
							rebuildRunBlocks()
						}
					}
					break
				}
			}
		}
	}

	async function retryLastRun() {
		if (!thread) return
		if (!selectedAgent) return
		runError = false
		isGenerating = true
		const runId = ++activeRun
		try {
			streamingAssistant = null
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent,
				input: optimisticUserMessage ? lastRunInput : null,
				runId,
			})
			if (runId !== activeRun) return
			runError = false
			optimisticUserMessage = null
			streamingAssistant = null
		} catch (e) {
			console.error('Failed to retry run', e)
			runError = true
			streamingAssistant = null
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	function handleStopGeneration() {
		// no server-side cancellation yet; this just ignores the in-flight response.
		activeRun++
		isGenerating = false
	}

	function handleCopyMessage(content: string) {
		navigator.clipboard.writeText(content)
	}

	function handleRegenerateMessage() {
		void retryLastRun()
	}

	function handleEditMessage(messageId: string) {
		console.log('Edit message:', messageId)
	}

	let confirmDeleteMessage = $state<{ id: string; preview: string } | null>(null)
	let isDeletingMessage = $state(false)
	let deleteMessageError = $state<string | null>(null)

	function requestDeleteUserMessage(messageId: string) {
		const msg = messages.find((m) => m.id === messageId)
		const preview = msg ? contentPartsToText(msg.content).trim() : ''
		confirmDeleteMessage = {
			id: messageId,
			preview: preview.length > 0 ? preview : 'this message',
		}
		deleteMessageError = null
	}

	async function deleteUserMessage(messageId: string): Promise<boolean> {
		if (!thread) return false
		if (isTemporaryChat) {
			const startIdx = messages.findIndex((m) => m.id === messageId)
			if (startIdx === -1) return false
			if (messages[startIdx]?.type !== 'user') return false
			const nextIdx = messages.findIndex((m, i) => i > startIdx && m.type === 'user')
			messages = messages.filter((_, i) => i < startIdx || (nextIdx !== -1 && i >= nextIdx))
			return true
		}

		const { response, error } = await v1Client().DELETE(
			'/threads/{thread_id}/messages/{message_id}',
			{
				params: {
					path: {
						thread_id: thread.id,
						message_id: messageId,
					},
				},
			}
		)
		if (!response.ok || error) {
			console.error('Failed to delete user message', error)
			return false
		}

		runError = false
		optimisticUserMessage = null
		streamingAssistant = null
		await loadBranch(thread.id)
		return true
	}

	const messageActionButtonClass =
		'flex h-6 w-6 cursor-pointer items-center justify-center text-white/80 transition-transform duration-150 hover:scale-[1.05] hover:text-white active:scale-[0.97]'

	let hasRenderableMessages = $derived(
		runBlocks.some((b) => b.items.length > 0) || optimisticUserMessage !== null || runError
	)
</script>

<div class="absolute inset-0 flex flex-col">
	{#if !autoScroll && hasRenderableMessages}
		<div
			class="pointer-events-none absolute inset-x-0 z-20 flex justify-center"
			style={`bottom: ${Math.max(24, inputOverlayHeight + 16)}px;`}
		>
			<button
				type="button"
				class="liquid-glass--frosted pointer-events-auto flex h-9 w-9 items-center justify-center rounded-full border border-white/10 text-white/85 transition-colors hover:bg-white/10 hover:text-white"
				aria-label="scroll to bottom"
				onclick={() => {
					autoScroll = true
					scrollToBottom('smooth')
				}}
			>
				<ArrowUp className="h-4 w-4 rotate-180" />
			</button>
		</div>
	{/if}

	<div
		class="relative flex-1 overflow-y-auto"
		style="view-transition-name: thread-body;"
		bind:this={scrollContainer}
		onscroll={handleScroll}
	>
		<div
			class="mx-auto flex min-h-full w-full max-w-7xl flex-col px-8"
			style={`padding-top: calc(var(--chrome-island-offset, 0px) + 16px); padding-bottom: ${Math.max(96, inputOverlayHeight + 24)}px;`}
		>
			{#if isTemporaryChat && hasLoadedBranch && messages.length === 0 && !optimisticUserMessage && !runError}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
						>
							<EyeSlash className="h-7 w-7" />
						</div>
						<h2 class="text-2xl font-semibold text-white/90">temporary chat enabled</h2>
						<p class="mt-2 text-sm text-white/60">
							send a message to start. messages here won’t be saved.
						</p>
					</div>
				</div>
			{:else if hasLoadedBranch && !hasRenderableMessages}
				<div class="flex flex-1 items-center justify-center py-16">
					<div class="max-w-md text-center">
						<div
							class="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-white/5 text-white/85"
						>
							<EyeSlash className="h-7 w-7" />
						</div>
						<h2 class="text-2xl font-semibold text-white/90">no messages yet</h2>
						<p class="mt-2 text-sm text-white/60">
							send a message to begin this thread.
						</p>
					</div>
				</div>
			{:else if hasLoadedBranch}
				<div class="flex flex-1 flex-col gap-6 py-4">
					{#each runBlocks as block (block.runId)}
						<div class="space-y-3">
							<!-- user messages for this run -->
							{#each block.items.filter((item) => item.kind === 'user') as item (item.message.id)}
								<UserChatMessage
									content={contentPartsToText(item.message.content)}
									timestamp={getMessageCreatedAt(item.message)}
									align={item.align}
								>
									{#snippet actions()}
										<button
											type="button"
											class={messageActionButtonClass}
											onclick={() =>
												handleCopyMessage(
													contentPartsToText(item.message.content)
												)}
											aria-label="copy message"
										>
											<DocumentDuplicate
												className="h-4 w-4"
												strokeWidth="2"
											/>
										</button>
										{#if item.align === 'right'}
											<button
												type="button"
												class={messageActionButtonClass}
												onclick={() => handleEditMessage(item.message.id)}
												aria-label="edit message"
											>
												<Pencil className="h-4 w-4" strokeWidth="2" />
											</button>
											<button
												type="button"
												class={messageActionButtonClass}
												onclick={() =>
													requestDeleteUserMessage(item.message.id)}
												aria-label="delete message"
											>
												<GarbageBin className="h-4 w-4" strokeWidth="2" />
											</button>
										{/if}
									{/snippet}
								</UserChatMessage>
							{/each}

							<!-- agent run (tools + response) rendered inside one assistant message UI -->
							{#key `${block.runId}-${toolTick}`}
								{@const toolCallIds = getBlockToolCallIds(block)}
								{@const lastAssistant = getBlockLastAssistantMessage(block)}
								{@const isStreamingBlock =
									blockHasStreamingAssistant(block) && streamingAssistant}

								{#if toolCallIds.length > 0 || lastAssistant || isStreamingBlock}
									<AssistantChatMessage
										content={isStreamingBlock
											? (streamingAssistant?.content ?? '')
											: lastAssistant
												? contentPartsToText(lastAssistant.content)
												: ''}
										timestamp={isStreamingBlock
											? (streamingAssistant?.timestamp ?? new Date())
											: lastAssistant
												? getMessageCreatedAt(lastAssistant)
												: undefined}
										isStreaming={Boolean(isStreamingBlock)}
										modelName={isStreamingBlock
											? streamingAssistant?.senderAgentId
												? (agentNameById.get(
														streamingAssistant.senderAgentId
													) ?? 'assistant')
												: 'assistant'
											: lastAssistant?.sender_agent_id
												? (agentNameById.get(
														lastAssistant.sender_agent_id
													) ?? 'assistant')
												: 'assistant'}
										avatarUrl={isStreamingBlock
											? streamingAssistant?.senderAgentId
												? (agentAvatarById.get(
														streamingAssistant.senderAgentId
													) ?? null)
												: null
											: lastAssistant?.sender_agent_id
												? (agentAvatarById.get(
														lastAssistant.sender_agent_id
													) ?? null)
												: null}
									>
										{#snippet lead()}
											{#each toolCallIds as toolCallId}
												{#if toolTracker.getExecution(toolCallId)}
													<ToolExecutionCard
														execution={toolTracker.getExecution(
															toolCallId
														)!}
													/>
												{/if}
											{/each}
										{/snippet}

										{#snippet actions()}
											<button
												type="button"
												class={messageActionButtonClass}
												onclick={() =>
													handleCopyMessage(
														isStreamingBlock
															? (streamingAssistant?.content ?? '')
															: lastAssistant
																? contentPartsToText(
																		lastAssistant.content
																	)
																: ''
													)}
												aria-label="copy message"
											>
												<DocumentDuplicate
													className="h-4 w-4"
													strokeWidth="2"
												/>
											</button>
											{#if !isStreamingBlock}
												<button
													type="button"
													class={messageActionButtonClass}
													onclick={handleRegenerateMessage}
													aria-label="retry"
												>
													<ArrowPath
														className="h-4 w-4"
														strokeWidth="2"
													/>
												</button>
											{/if}
										{/snippet}
									</AssistantChatMessage>
								{/if}
							{/key}
						</div>
					{/each}

					{#if optimisticUserMessage}
						<div in:fade={{ duration: 200 }}>
							<UserChatMessage
								content={optimisticUserMessage.content}
								timestamp={optimisticUserMessage.timestamp}
							>
								{#snippet actions()}
									<button
										type="button"
										class={messageActionButtonClass}
										onclick={() =>
											handleCopyMessage(optimisticUserMessage?.content ?? '')}
										aria-label="copy message"
									>
										<DocumentDuplicate className="h-4 w-4" strokeWidth="2" />
									</button>
								{/snippet}
							</UserChatMessage>
						</div>
					{/if}

					{#if runError}
						<div in:fade={{ duration: 200 }}>
							<AssistantChatMessage
								content={selectedAgent
									? 'there was an error generating a response.'
									: 'select an agent to generate a response.'}
								modelName={selectedAgentName}
								isLastMessage={true}
								tone="error"
							>
								{#snippet actions()}
									<Button variant="glass" size="sm" onclick={retryLastRun}>
										retry
									</Button>
								{/snippet}
							</AssistantChatMessage>
						</div>
					{/if}

					<!-- streaming assistant is rendered within its run block -->
				</div>
			{:else}
				<!-- while data is loading, keep layout stable; loader is rendered as an overlay -->
				<div class="flex-1"></div>
			{/if}
		</div>

		{#if showThreadLoader}
			<div
				class="pointer-events-none absolute inset-0 flex items-center justify-center"
				in:fade={{ duration: 120 }}
				out:fade={{ duration: 260 }}
			>
				<NokodoLoader className="opacity-80" shimmer expanded />
			</div>
		{/if}
	</div>

	<div class="absolute right-0 bottom-0 left-0 z-10 pt-4 pb-5" bind:this={inputOverlay}>
		<div class="relative mx-auto w-full max-w-7xl px-8">
			<div
				style="view-transition-name: chat-input;"
				class="transition-all duration-500 ease-in-out"
			>
				<ChatInputLiquidGlass
					bind:value={inputValue}
					onSubmit={handleSendMessage}
					onStop={handleStopGeneration}
					{isGenerating}
					placeholder="send a message"
				/>
			</div>
		</div>
	</div>
</div>

{#if confirmDeleteMessage}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-60 flex items-center justify-center bg-black/55 px-6"
		onclick={() => {
			if (!isDeletingMessage) {
				confirmDeleteMessage = null
				deleteMessageError = null
			}
		}}
	>
		<div
			class="liquid-glass rounded-container w-full max-w-sm px-6 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.6)]"
			onclick={(e) => e.stopPropagation()}
		>
			<span class="liquid-glass__highlight" aria-hidden="true"></span>
			<div class="liquid-glass__content">
				<div class="text-lg font-semibold text-white/90">delete message?</div>
				<div class="mt-2 text-sm text-white/60">{confirmDeleteMessage.preview}</div>

				{#if deleteMessageError}
					<div
						class="mt-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/70"
					>
						{deleteMessageError}
					</div>
				{/if}

				<div class="mt-5 flex items-center justify-end gap-2">
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-transparent px-4 py-2 text-sm text-white/80 transition-colors duration-150 hover:bg-white/5"
						disabled={isDeletingMessage}
						onclick={() => {
							confirmDeleteMessage = null
							deleteMessageError = null
						}}
					>
						cancel
					</button>
					<button
						type="button"
						class="rounded-2xl border border-white/10 bg-white/10 px-4 py-2 text-sm text-white/90 transition-colors duration-150 hover:bg-white/15 disabled:opacity-60"
						disabled={isDeletingMessage}
						onclick={() => {
							void (async () => {
								if (!confirmDeleteMessage) return
								isDeletingMessage = true
								deleteMessageError = null
								try {
									const ok = await deleteUserMessage(confirmDeleteMessage.id)
									if (!ok) {
										deleteMessageError = 'could not delete message'
										return
									}
									confirmDeleteMessage = null
								} catch {
									deleteMessageError = 'could not delete message'
								} finally {
									isDeletingMessage = false
								}
							})()
						}}
					>
						{isDeletingMessage ? 'deleting…' : 'delete'}
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}

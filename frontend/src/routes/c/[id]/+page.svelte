<script lang="ts">
	import { page } from '$app/state'
	import { eventStreamClient, runChatStream, type StreamEvent } from '$lib/api/streaming'
	import type { components } from '$lib/api/types'
	import { v1Client } from '$lib/api/v1/client'
	import AssistantChatMessage from '$lib/components/chat/AssistantChatMessage.svelte'
	import ChatInputLiquidGlass from '$lib/components/chat/ChatInput.svelte'
	import Connecting from '$lib/components/chat/Connecting.svelte'
	import MessageActionButton from '$lib/components/chat/MessageActionButton.svelte'
	import ToolExecutionCard from '$lib/components/chat/ToolExecutionCard.svelte'
	import UserChatMessage from '$lib/components/chat/UserChatMessage.svelte'
	import ArrowPath from '$lib/components/icons/ArrowPath.svelte'
	import ArrowUp from '$lib/components/icons/ArrowUp.svelte'
	import DocumentDuplicate from '$lib/components/icons/DocumentDuplicate.svelte'
	import EyeSlash from '$lib/components/icons/EyeSlash.svelte'
	import GarbageBin from '$lib/components/icons/GarbageBin.svelte'
	import Pencil from '$lib/components/icons/Pencil.svelte'
	import MarkdownRenderer from '$lib/components/markdown/MarkdownRenderer.svelte'
	import NokodoLoader from '$lib/components/NokodoLoader.svelte'
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
		responseRootId: string | null
	}

	interface StreamingAssistantState {
		runId: string | null
		messageId: string
		content: string
		timestamp: Date
		senderAgentId: string | null
		toolCalls: ToolCall[]
	}

	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let selectedAgent = $state('')
	let didLoadAgents = $state(false)
	let optimisticUserMessage = $state<{ content: string; timestamp: Date } | null>(null)
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let streamingAssistantParentId = $state<string | null>(null)
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

	let messageTree = new SvelteMap<string, ApiMessage>()
	let messageChildren = $derived.by(() => {
		const map = new SvelteMap<string | null, string[]>()
		for (const msg of messageTree.values()) {
			const pid = msg.parent_id ?? null
			const existing = map.get(pid) ?? []
			existing.push(msg.id)
			map.set(pid, existing)
		}
		// Sort children by created_at
		for (const [, kids] of map) {
			kids.sort((a, b) => {
				const ma = messageTree.get(a)
				const mb = messageTree.get(b)
				if (!ma || !mb) return 0
				return getMessageCreatedAt(ma).getTime() - getMessageCreatedAt(mb).getTime()
			})
		}
		return map
	})

	let currentLeafId = $state<string | null>(null)

	// Reconstruct the active branch from root to currentLeafId
	let messages = $derived.by(() => {
		if (!currentLeafId) return []
		const branch: ApiMessage[] = []
		let curr: string | null = currentLeafId
		while (curr) {
			const msg = messageTree.get(curr)
			if (!msg) break
			branch.unshift(msg)
			curr = msg.parent_id ?? null
		}
		return branch
	})

	function contentPartsToText(parts: ApiMessage['content']): string {
		if (!parts || parts.length === 0) return ''
		return parts
			.map((part) => {
				if (!part) return ''
				if (part.type === 'text') {
					return 'text' in part && typeof part.text === 'string' ? part.text : ''
				}
				if (part.type === 'refusal') {
					return 'reason' in part && typeof part.reason === 'string' ? part.reason : ''
				}
				if (part.type === 'json') {
					try {
						return 'data' in part ? JSON.stringify(part.data) : ''
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

	function getLatestLeaf(rootId: string): string {
		let curr = rootId
		while (true) {
			const kids = messageChildren.get(curr)
			if (!kids || kids.length === 0) return curr
			curr = kids[kids.length - 1]
		}
	}

	function switchBranch(messageId: string, direction: 'prev' | 'next') {
		const msg = messageTree.get(messageId)
		if (!msg) return
		const parentId = msg.parent_id ?? null
		const siblings = messageChildren.get(parentId) ?? []
		if (siblings.length <= 1) return

		const idx = siblings.indexOf(messageId)
		if (idx === -1) return

		const targetIdx = direction === 'prev' ? idx - 1 : idx + 1
		if (targetIdx < 0 || targetIdx >= siblings.length) return

		const targetId = siblings[targetIdx]
		const newLeaf = getLatestLeaf(targetId)
		currentLeafId = newLeaf
		rebuildRunBlocks()
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
			const block: RunBlock = {
				runId,
				startedAt,
				title,
				items: [],
				responseRootId: null,
			}
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

			// mark the first assistant/tool message as the response root for branch navigation
			if (block.responseRootId === null) {
				block.responseRootId = msg.id
			}

			if (msg.type === 'assistant') {
				// add text content first (text comes before tool calls in a turn)
				const text = contentPartsToText(msg.content).trim()
				if (text.length > 0) block.items.push({ kind: 'assistant', message: msg })
				// then add tool calls
				for (const tc of parseToolCalls(msg)) {
					toolTracker.registerToolCall(tc)
					if (!seen.has(tc.id)) {
						seen.add(tc.id)
						block.items.push({ kind: 'tool', toolCallId: tc.id })
					}
				}
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
			if (block.responseRootId === null) {
				block.responseRootId = streamingAssistant.messageId
			}

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

	function getBlockResponseItems(
		block: RunBlock
	): Array<
		| { kind: 'assistant'; message: ApiMessage }
		| { kind: 'tool'; toolCallId: string }
		| { kind: 'streaming_assistant' }
		| { kind: 'streaming_tool'; toolCallId: string }
	> {
		return block.items.filter(
			(
				item
			): item is Exclude<
				RunItem,
				{ kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
			> => item.kind !== 'user'
		)
	}

	function getBlockFirstAssistant(block: RunBlock): ApiMessage | null {
		const item = block.items.find((i) => i.kind === 'assistant')
		return item?.kind === 'assistant' ? item.message : null
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

	async function loadTree(threadId: string): Promise<boolean> {
		const { data, error } = await v1Client().GET('/threads/{thread_id}/tree', {
			params: { path: { thread_id: threadId } },
		})
		if (error) {
			console.error('failed to load thread tree', error)
			messageTree.clear()
			currentLeafId = null
			return false
		}
		toolTracker.clear()
		const msgs = (data ?? []) as ApiMessage[]
		messageTree.clear()
		for (const msg of msgs) {
			messageTree.set(msg.id, msg)
			if (msg.type === 'assistant') {
				for (const tc of parseToolCalls(msg)) toolTracker.registerToolCall(tc)
			}
			if (msg.type === 'tool') {
				const result = parseToolResult(msg)
				if (result) toolTracker.registerResult(result)
			}
		}
		currentLeafId = thread?.current_message_id ?? null

		await fetchToolEventsForThread(
			threadId,
			msgs.filter((m) => m.type === 'assistant').map((m) => m.id)
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
			messageTree.clear()
			currentLeafId = null
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
					hasLoadedBranch = await loadTree(data.id)
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
			messageTree.clear()
			currentLeafId = null
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
			console.error('failed to run thread', e)
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
		parentId?: string | null
	}): Promise<void> {
		runAbortController?.abort()
		runAbortController = new AbortController()

		let assistantParentId = opts.parentId ?? currentLeafId
		streamingAssistantParentId = assistantParentId

		// when retrying, switch view to parent so new response replaces old branch
		if (!opts.input) {
			if (assistantParentId) currentLeafId = assistantParentId
			else currentLeafId = null
		}

		for await (const delta of runChatStream({
			threadId: opts.threadId,
			agentId: opts.agentId,
			input: opts.input,
			parentId: opts.parentId,
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
					if (msg.type === 'user') {
						optimisticUserMessage = null
					}
					messageTree.set(msg.id, msg)
					currentLeafId = msg.id
					// keep parent chain updated for subsequent messages in this run
					assistantParentId = msg.id
					streamingAssistantParentId = msg.id
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
							const now = new Date().toISOString()
							const finalized = {
								id: streamingAssistant.messageId,
								thread_id: opts.threadId,
								parent_id: assistantParentId,
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
								created_at: now,
								updated_at: now,
							} satisfies ApiMessage
							if (!messageTree.has(finalized.id)) {
								messageTree.set(finalized.id, finalized)
								currentLeafId = finalized.id
							}
							// update parent chain for next message in this run
							assistantParentId = finalized.id
							streamingAssistantParentId = finalized.id
							streamingAssistant = null
							rebuildRunBlocks()
						}
					}
					break
				}
			}
		}
	}

	async function handleRegenerateMessage(parentId: string | null = null) {
		if (!thread) return
		if (!selectedAgent) return
		runError = false
		isGenerating = true

		// Initialize placeholder for immediate UI feedback
		streamingAssistantParentId = parentId ?? currentLeafId
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

		try {
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent,
				input: optimisticUserMessage ? lastRunInput : null,
				runId,
				parentId,
			})
			if (runId !== activeRun) return
			runError = false
			optimisticUserMessage = null
			streamingAssistant = null
			streamingAssistantParentId = null
		} catch (e) {
			console.error('failed to retry run', e)
			runError = true
			streamingAssistant = null
			streamingAssistantParentId = null
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

	async function handleEditMessage(messageId: string) {
		if (!thread) return
		const msg = messages.find((m) => m.id === messageId)
		if (!msg) return

		const currentContent = contentPartsToText(msg.content)
		const newContent = window.prompt('edit message', currentContent)

		if (newContent === null || newContent.trim() === currentContent.trim()) return
		if (!newContent.trim()) return

		const body = {
			content: newContent,
			type: 'user',
			parent_id: msg.parent_id ?? null,
		} satisfies components['schemas']['MessageCreate']

		const { data: newMessage, error } = await v1Client().POST('/threads/{thread_id}/messages', {
			params: { path: { thread_id: thread.id } },
			body,
		})

		if (error || !newMessage) {
			console.error('failed to create edited message', error)
			return
		}

		messageTree.set(newMessage.id, newMessage)
		currentLeafId = newMessage.id
		rebuildRunBlocks()

		await handleRegenerateMessage(newMessage.id)
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
			const start = messageTree.get(messageId)
			if (!start || start.type !== 'user') return false

			const idsToDelete: string[] = []
			const stack: string[] = [messageId]
			while (stack.length > 0) {
				const id = stack.pop()
				if (!id) continue
				idsToDelete.push(id)
				const kids = messageChildren.get(id) ?? []
				for (const childId of kids) stack.push(childId)
			}

			for (const id of idsToDelete) messageTree.delete(id)
			currentLeafId = start.parent_id ?? null
			rebuildRunBlocks()
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
			console.error('failed to delete user message', error)
			return false
		}

		runError = false
		optimisticUserMessage = null
		streamingAssistant = null
		await loadTree(thread.id)
		return true
	}

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
								{@const siblings =
									messageChildren.get(item.message.parent_id ?? null) ?? []}
								<UserChatMessage
									content={contentPartsToText(item.message.content)}
									timestamp={getMessageCreatedAt(item.message)}
									align={item.align}
									siblingCount={siblings.length}
									currentSiblingIndex={siblings.indexOf(item.message.id)}
									onPrevious={() => switchBranch(item.message.id, 'prev')}
									onNext={() => switchBranch(item.message.id, 'next')}
								>
									{#snippet actions()}
										<MessageActionButton
											onclick={() =>
												handleCopyMessage(
													contentPartsToText(item.message.content)
												)}
											ariaLabel="copy message"
										>
											<DocumentDuplicate
												className="h-4 w-4"
												strokeWidth="2"
											/>
										</MessageActionButton>
										{#if item.align === 'right'}
											<MessageActionButton
												onclick={() => handleEditMessage(item.message.id)}
												ariaLabel="edit message"
											>
												<Pencil className="h-4 w-4" strokeWidth="2" />
											</MessageActionButton>
											<MessageActionButton
												onclick={() =>
													requestDeleteUserMessage(item.message.id)}
												ariaLabel="delete message"
											>
												<GarbageBin className="h-4 w-4" strokeWidth="2" />
											</MessageActionButton>
										{/if}
									{/snippet}
								</UserChatMessage>
							{/each}

							<!-- agent run: render ALL items in chronological order -->
							{#key `${block.runId}-${toolTick}`}
								{@const responseItems = getBlockResponseItems(block)}
								{@const firstAssistant = getBlockFirstAssistant(block)}
								{@const isStreamingBlock =
									blockHasStreamingAssistant(block) && streamingAssistant}

								{#if responseItems.length > 0 || isStreamingBlock}
									{@const rootId = block.responseRootId}
									{@const blockParentId =
										(rootId
											? (messageTree.get(rootId)?.parent_id ?? null)
											: null) ??
										(isStreamingBlock ? streamingAssistantParentId : null)}
									{@const assistantSiblings =
										messageChildren.get(blockParentId) ?? []}
									{@const currentSiblingIndex = rootId
										? isStreamingBlock && !messageTree.has(rootId)
											? assistantSiblings.length
											: assistantSiblings.indexOf(rootId)
										: 0}
									{@const siblingCount =
										assistantSiblings.length +
										(isStreamingBlock && !messageTree.has(rootId ?? '')
											? 1
											: 0)}
									{@const displayAgent =
										firstAssistant?.sender_agent_id ??
										streamingAssistant?.senderAgentId ??
										null}

									<AssistantChatMessage
										{siblingCount}
										{currentSiblingIndex}
										onPrevious={() => rootId && switchBranch(rootId, 'prev')}
										onNext={() => rootId && switchBranch(rootId, 'next')}
										content=""
										timestamp={firstAssistant
											? getMessageCreatedAt(firstAssistant)
											: isStreamingBlock
												? (streamingAssistant?.timestamp ?? new Date())
												: undefined}
										isStreaming={Boolean(isStreamingBlock)}
										modelName={displayAgent
											? (agentNameById.get(displayAgent) ?? 'assistant')
											: 'assistant'}
										avatarUrl={displayAgent
											? (agentAvatarById.get(displayAgent) ?? null)
											: null}
									>
										{#snippet lead()}
											{#each responseItems as item, idx (idx)}
												{#if item.kind === 'assistant'}
													<div
														class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
													>
														<MarkdownRenderer
															content={contentPartsToText(
																item.message.content
															)}
															isStreaming={false}
														/>
													</div>
												{:else if item.kind === 'tool'}
													{@const exec = toolTracker.getExecution(
														item.toolCallId
													)}
													{#if exec}
														<ToolExecutionCard execution={exec} />
													{/if}
												{:else if item.kind === 'streaming_tool'}
													{@const exec = toolTracker.getExecution(
														item.toolCallId
													)}
													{#if exec}
														<ToolExecutionCard execution={exec} />
													{/if}
												{:else if item.kind === 'streaming_assistant' && streamingAssistant}
													{#if streamingAssistant.content.trim()}
														<div
															class="assistant-markdown text-[0.95rem] leading-relaxed wrap-break-word"
														>
															<MarkdownRenderer
																content={streamingAssistant.content}
																isStreaming={true}
															/>
														</div>
													{:else}
														<div
															class="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-[0.95rem] leading-relaxed text-white/60"
														>
															<Connecting />
														</div>
													{/if}
												{/if}
											{/each}
										{/snippet}

										{#snippet actions()}
											<MessageActionButton
												onclick={() => {
													const allText = responseItems
														.filter(
															(
																i
															): i is {
																kind: 'assistant'
																message: ApiMessage
															} => i.kind === 'assistant'
														)
														.map((i) =>
															contentPartsToText(i.message.content)
														)
														.join('\n\n')
													const streamText = isStreamingBlock
														? (streamingAssistant?.content ?? '')
														: ''
													handleCopyMessage(
														allText +
															(streamText ? '\n\n' + streamText : '')
													)
												}}
												ariaLabel="copy message"
											>
												<DocumentDuplicate
													className="h-4 w-4"
													strokeWidth="2"
												/>
											</MessageActionButton>
											{#if !isStreamingBlock}
												<MessageActionButton
													onclick={() => {
														const userItem = block.items.find(
															(i) => i.kind === 'user'
														)
														const lastAssistant =
															getBlockLastAssistantMessage(block)
														const parentId = userItem
															? userItem.message.id
															: (lastAssistant?.parent_id ?? null)
														handleRegenerateMessage(parentId)
													}}
													ariaLabel="retry"
												>
													<ArrowPath
														className="h-4 w-4"
														strokeWidth="2"
													/>
												</MessageActionButton>
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
									<MessageActionButton
										onclick={() =>
											handleCopyMessage(optimisticUserMessage?.content ?? '')}
										ariaLabel="copy message"
									>
										<DocumentDuplicate className="h-4 w-4" strokeWidth="2" />
									</MessageActionButton>
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
									<button
										type="button"
										class="rounded-xl bg-transparent px-3 py-1.5 text-sm text-white/70 transition-colors hover:text-white/95"
										onclick={() => handleRegenerateMessage()}
									>
										retry
									</button>
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
			<div class="transition-all duration-500 ease-in-out">
				<ChatInputLiquidGlass
					bind:value={inputValue}
					onSubmit={handleSendMessage}
					onStop={handleStopGeneration}
					{isGenerating}
					placeholder="send a message"
					viewTransitionName="chat-input"
				/>
			</div>
		</div>
	</div>
</div>

{#if confirmDeleteMessage}
	<div
		class="fixed inset-0 z-60 flex items-center justify-center bg-black/55 px-6"
		role="button"
		tabindex="0"
		onclick={() => {
			if (!isDeletingMessage) {
				confirmDeleteMessage = null
				deleteMessageError = null
			}
		}}
		onkeydown={(e) => {
			if (isDeletingMessage) return
			if (e.key === 'Escape' || e.key === 'Enter' || e.key === ' ') {
				confirmDeleteMessage = null
				deleteMessageError = null
			}
		}}
	>
		<div
			class="liquid-glass rounded-container w-full max-w-sm px-6 py-5 shadow-[0_32px_64px_rgba(12,10,30,0.6)]"
			role="dialog"
			aria-modal="true"
			tabindex="-1"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
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

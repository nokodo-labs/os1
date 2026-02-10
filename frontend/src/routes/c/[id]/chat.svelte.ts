/**
 * reactive chat state management using Svelte 5 runes.
 * encapsulates all chat page state and business logic.
 */

import { apiClient } from '$lib/api/client'
import { eventStreamClient, runChatStream, type StreamEvent } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { agents } from '$lib/stores/agents.svelte'
import { chat as chatStore, type Thread } from '$lib/stores/chat.svelte'
import { selectedAgent } from '$lib/stores/selectedAgent.svelte'
import { session } from '$lib/stores/session.svelte'
import {
	ToolExecutionTracker,
	parseToolCalls,
	parseToolEvent,
	parseToolResult,
	type ToolCall,
} from '$lib/tools'
import { hapticFeedback } from '$lib/utils/haptics'
import { tick } from 'svelte'
import { SvelteDate, SvelteMap, SvelteSet } from 'svelte/reactivity'
import {
	computeIsAtBottom,
	contentPartsToText,
	getMessageCreatedAt,
	getRunId,
	sdkPartsToText,
} from './chatHelpers'

export type ApiMessage = components['schemas']['Message']
type ApiEvent = components['schemas']['Event']

export type RunItem =
	| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
	| { kind: 'optimistic_user'; content: string; timestamp: Date }
	| { kind: 'assistant'; message: ApiMessage }
	| { kind: 'tool'; toolCallId: string }
	| { kind: 'streaming_assistant' }
	| { kind: 'streaming_tool'; toolCallId: string }

export interface RunBlock {
	runId: string
	title: string
	startedAt: Date
	items: RunItem[]
	responseRootId: string | null
}

export interface StreamingAssistantState {
	runId: string | null
	messageId: string
	content: string
	timestamp: Date
	senderAgentId: string | null
	toolCalls: ToolCall[]
}

/**
 * creates the reactive chat state for a thread page.
 * returns an object with all state and methods needed by the UI.
 */
export function createChatState() {
	// ─────────────────────────────────────────────────────────────────────────────
	// core state
	// ─────────────────────────────────────────────────────────────────────────────
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let optimisticUserMessage = $state<{ content: string; timestamp: Date } | null>(null)
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let streamingAssistantParentId = $state<string | null>(null)
	let viewingStreamingBranch = $state(true)
	let streamingLeafId = $state<string | null>(null)
	let runError = $state(false)
	let lastRunInput = $state('')
	let runBlocks = $state<RunBlock[]>([])

	// thread state
	let thread = $state<Thread | null>(null)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)

	// message paging (latest-first from backend)
	let messageSkip = $state(0)
	let hasMoreMessages = $state(true)
	let isLoadingOlderMessages = $state(false)

	// message tree (for branching)
	const messageTree = new SvelteMap<string, ApiMessage>()
	let currentLeafId = $state<string | null>(null)

	// scroll state
	let scrollContainer = $state<HTMLElement | null>(null)
	let inputOverlay = $state<HTMLElement | null>(null)
	let autoScroll = $state(true)
	let initialScrollDone = $state(false)
	let lastThreadId = $state<string | null>(null)
	let inputOverlayHeight = $state(0)
	let scrollQueued = false

	// tool tracking
	const toolTracker = new ToolExecutionTracker()
	let toolTick = $state(0)
	const fetchedToolEventMessageIds = new SvelteSet<string>()
	const toolEventsPendingIds = new SvelteSet<string>()
	let toolEventsInFlight = $state(false)

	function getToolExecution(toolCallId: string) {
		if (toolTick < 0) return null
		return toolTracker.getExecution(toolCallId)
	}

	// delete confirmation
	let confirmDeleteMessage = $state<{ id: string; preview: string } | null>(null)
	let isDeletingMessage = $state(false)
	let deleteMessageError = $state<string | null>(null)

	// abort controller for streaming
	let runAbortController: AbortController | null = null

	// ─────────────────────────────────────────────────────────────────────────────
	// derived state
	// ─────────────────────────────────────────────────────────────────────────────
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)
	const showThreadLoader = $derived(isThreadLoading)
	const currentUserId = $derived(session.currentUser?.id ?? null)

	const messageChildren = $derived.by(() => {
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

	// reconstruct the active branch from root to currentLeafId
	const messages = $derived.by(() => {
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

	const hasRenderableMessages = $derived(
		runBlocks.some((b) => b.items.length > 0) || optimisticUserMessage !== null || runError
	)

	const agentNameById = $derived(new SvelteMap(agents.list.map((a) => [a.id, a.name])))
	const agentAvatarById = $derived(
		new SvelteMap(agents.list.map((a) => [a.id, a.profile_image_url ?? null]))
	)
	// ─────────────────────────────────────────────────────────────────────────────
	// tool call helpers
	// ─────────────────────────────────────────────────────────────────────────────
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

	// ─────────────────────────────────────────────────────────────────────────────
	// run block management
	// ─────────────────────────────────────────────────────────────────────────────
	function rebuildRunBlocks(): void {
		const sorted = messages.slice().sort((a, b) => {
			return getMessageCreatedAt(a).getTime() - getMessageCreatedAt(b).getTime()
		})

		const blocks: RunBlock[] = []
		const byRun = new SvelteMap<string, RunBlock>()
		const seenToolCalls = new SvelteMap<string, SvelteSet<string>>()
		const userId = currentUserId

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
			// skip the message currently being streamed — the streaming overlay handles it
			if (streamingAssistant && msg.id === streamingAssistant.messageId) continue

			const runId = getRunId(msg)
			const block = ensureBlock(runId, getMessageCreatedAt(msg), 'assistant')
			let seen = seenToolCalls.get(runId)
			if (!seen) {
				seen = new SvelteSet()
				seenToolCalls.set(runId, seen)
			}

			if (msg.type === 'user') {
				const align: 'left' | 'right' =
					userId && msg.sender_user_id && msg.sender_user_id !== userId ? 'left' : 'right'
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

		if (streamingAssistant && viewingStreamingBranch) {
			const runId = streamingAssistant.runId ?? `legacy-${streamingAssistant.messageId}`
			const block = ensureBlock(runId, streamingAssistant.timestamp, 'assistant')

			// add optimistic user message to this run block (before assistant response)
			// this ensures user message and streaming assistant appear in correct order
			if (optimisticUserMessage) {
				block.items.push({
					kind: 'optimistic_user',
					content: optimisticUserMessage.content,
					timestamp: optimisticUserMessage.timestamp,
				})
			}

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
		} else if (optimisticUserMessage && viewingStreamingBranch) {
			// optimistic user message exists but no streaming assistant yet
			// create a standalone block for the pending user message
			const runId = `pending-user-${optimisticUserMessage.timestamp.getTime()}`
			const block = ensureBlock(runId, optimisticUserMessage.timestamp, 'pending')
			block.items.push({
				kind: 'optimistic_user',
				content: optimisticUserMessage.content,
				timestamp: optimisticUserMessage.timestamp,
			})
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
				| { kind: 'user'; message: ApiMessage; align: 'left' | 'right' }
				| { kind: 'optimistic_user'; content: string; timestamp: Date }
			> => item.kind !== 'user' && item.kind !== 'optimistic_user'
		)
	}

	function getBlockFirstAssistant(block: RunBlock): ApiMessage | null {
		const item = block.items.find((i) => i.kind === 'assistant')
		return item?.kind === 'assistant' ? item.message : null
	}

	function blockHasStreamingAssistant(block: RunBlock): boolean {
		return block.items.some((item) => item.kind === 'streaming_assistant')
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// branch navigation
	// ─────────────────────────────────────────────────────────────────────────────
	function getLatestLeaf(rootId: string): string {
		let curr = rootId
		while (true) {
			const kids = messageChildren.get(curr)
			if (!kids || kids.length === 0) return curr
			curr = kids[kids.length - 1]
		}
	}

	/** check if a leaf node is on the streaming branch by walking up to the streaming leaf */
	function isOnStreamingBranch(leafId: string): boolean {
		if (!streamingLeafId) {
			// if we haven't created the message yet, we are on the streaming branch
			// only if we are sitting at the parent (waiting for it)
			return streamingAssistantParentId ? leafId === streamingAssistantParentId : true
		}
		let curr: string | null = streamingLeafId
		while (curr) {
			if (curr === leafId) return true
			const msg = messageTree.get(curr)
			if (!msg) break
			curr = msg.parent_id ?? null
		}
		return false
	}

	async function switchBranch(messageId: string, direction: 'prev' | 'next') {
		let parentId: string | null
		let siblings: string[]
		let idx: number
		let pendingVirtual = false

		const msg = messageTree.get(messageId)
		if (msg) {
			parentId = msg.parent_id ?? null
			siblings = messageChildren.get(parentId) ?? []
			idx = siblings.indexOf(messageId)
		} else if (isGenerating && streamingAssistantParentId) {
			// pending streaming placeholder not yet in the tree
			parentId = streamingAssistantParentId
			siblings = messageChildren.get(parentId) ?? []
			idx = siblings.length // virtual last entry
			pendingVirtual = true
		} else {
			return
		}

		if (idx === -1) return

		const totalCount = siblings.length + (pendingVirtual ? 1 : 0)
		if (totalCount <= 1) return

		const targetIdx = direction === 'prev' ? idx - 1 : idx + 1
		if (targetIdx < 0 || targetIdx >= totalCount) return

		// navigating back to the virtual pending entry (only during the brief pre-delta window)
		if (pendingVirtual && targetIdx >= siblings.length) {
			viewingStreamingBranch = true
			currentLeafId = streamingLeafId ?? streamingAssistantParentId
			rebuildRunBlocks()
			return
		}

		const targetId = siblings[targetIdx]
		const newLeaf = getLatestLeaf(targetId)

		if (isGenerating) {
			const onStreaming = isOnStreamingBranch(newLeaf)
			viewingStreamingBranch = onStreaming
			currentLeafId = onStreaming && streamingLeafId ? streamingLeafId : newLeaf
			rebuildRunBlocks()
			return
		}

		currentLeafId = newLeaf
		rebuildRunBlocks()

		// persist branch selection to backend
		if (thread) {
			try {
				await apiClient().PATCH('/v1/threads/{thread_id}', {
					params: { path: { thread_id: thread.id } },
					body: { current_message_id: newLeaf },
				})
				thread = { ...thread, current_message_id: newLeaf }
			} catch (e) {
				console.error('failed to persist branch selection', e)
			}
		}
	}

	/**
	 * find the user message that started a run by walking up from the response root.
	 */
	function findRunUserMessage(block: RunBlock): string | null {
		const firstResponseId = block.responseRootId
		if (!firstResponseId) return null
		const firstResponse = messageTree.get(firstResponseId)
		if (!firstResponse) return null
		// Walk up to find the user message
		let parentId = firstResponse.parent_id
		while (parentId) {
			const parent = messageTree.get(parentId)
			if (!parent) break
			if (parent.type === 'user') return parent.id
			parentId = parent.parent_id
		}
		return null
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// scroll management
	// ─────────────────────────────────────────────────────────────────────────────
	function handleScroll() {
		if (!scrollContainer) return
		const atBottom = computeIsAtBottom(scrollContainer)
		if (atBottom !== autoScroll) autoScroll = atBottom
		// avoid runaway paging during initial mount/auto-scroll.
		// initialScrollDone is set once we have loaded and pinned to bottom.
		if (!initialScrollDone) return
		if (scrollContainer.scrollTop <= 80) {
			const threadId = thread?.id
			if (!threadId) return
			if (!hasMoreMessages) return
			if (isLoadingOlderMessages) return
			void loadOlderMessages(threadId)
		}
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

	// ─────────────────────────────────────────────────────────────────────────────
	// data loading
	// ─────────────────────────────────────────────────────────────────────────────
	async function fetchToolEventsForThread(threadId: string, msgIds: string[]): Promise<void> {
		if (msgIds.length === 0) return

		// queue IDs that haven't been fetched yet
		for (const id of msgIds) {
			if (!fetchedToolEventMessageIds.has(id)) {
				toolEventsPendingIds.add(id)
			}
		}

		// if already fetching, the current fetch will pick up queued IDs on completion
		if (toolEventsInFlight) return

		// process all pending IDs
		while (toolEventsPendingIds.size > 0) {
			const batch = Array.from(toolEventsPendingIds)
			toolEventsPendingIds.clear()

			toolEventsInFlight = true
			try {
				const { data, error } = await apiClient().POST(
					'/v1/threads/{thread_id}/events/by-message-ids',
					{
						params: { path: { thread_id: threadId } },
						body: { message_ids: batch },
					}
				)
				if (!error && data) {
					for (const ev of data as ApiEvent[]) {
						const toolEv = parseToolEvent({
							id: ev.id,
							type: ev.type,
							data: (ev.data ?? {}) as Record<string, unknown>,
							created_at: ev.created_at ?? undefined,
							message_id: ev.message_id ?? undefined,
						})
						if (toolEv) toolTracker.processEvent(toolEv)
					}
					toolTick++
				}
				for (const id of batch) fetchedToolEventMessageIds.add(id)
			} finally {
				toolEventsInFlight = false
			}
		}
	}

	function ingestMessages(msgs: ApiMessage[]): void {
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
	}

	async function loadOlderMessages(threadId: string): Promise<void> {
		if (!scrollContainer) return
		if (isLoadingOlderMessages) return
		if (!hasMoreMessages) return

		isLoadingOlderMessages = true
		const prevScrollHeight = scrollContainer.scrollHeight
		const prevScrollTop = scrollContainer.scrollTop

		try {
			const { data, error } = await apiClient().GET('/v1/threads/{thread_id}/messages', {
				params: {
					path: { thread_id: threadId },
					query: { skip: messageSkip, limit: 120 },
				},
			})
			if (error) return
			const page = (data ?? []) as ApiMessage[]
			if (page.length === 0) {
				hasMoreMessages = false
				return
			}
			messageSkip += page.length
			ingestMessages(page)

			await fetchToolEventsForThread(
				threadId,
				page.filter((m) => m.type === 'assistant').map((m) => m.id)
			)

			await tick()
			const newScrollHeight = scrollContainer.scrollHeight
			scrollContainer.scrollTop = prevScrollTop + (newScrollHeight - prevScrollHeight)
		} finally {
			isLoadingOlderMessages = false
		}
	}

	async function loadTree(threadId: string): Promise<boolean> {
		// try cache first for instant load
		const cachedThread = chatStore.threadCache.get(threadId)
		const cachedMessages = chatStore.threadCache.getCachedMessages(threadId)

		let threadData: typeof cachedThread
		let messagesPage: ApiMessage[]

		if (cachedThread && cachedMessages) {
			// use cached data for instant render
			threadData = cachedThread
			messagesPage = cachedMessages
		} else {
			// fetch from API
			const { data, error: threadError } = await apiClient().GET('/v1/threads/{thread_id}', {
				params: { path: { thread_id: threadId } },
			})
			if (threadError) {
				console.error('failed to load thread', threadError)
				thread = null
				chatStore.activeThread = null
				toolTracker.clear()
				messageTree.clear()
				currentLeafId = null
				rebuildRunBlocks()
				return false
			}
			if (!data) {
				thread = null
				chatStore.activeThread = null
				toolTracker.clear()
				messageTree.clear()
				currentLeafId = null
				rebuildRunBlocks()
				return true
			}
			threadData = data

			const { data: msgData, error: msgError } = await apiClient().GET(
				'/v1/threads/{thread_id}/messages',
				{ params: { path: { thread_id: threadId }, query: { skip: 0, limit: 120 } } }
			)
			if (msgError) {
				console.error('failed to load messages', msgError)
				currentLeafId = null
				return false
			}
			messagesPage = (msgData ?? []) as ApiMessage[]

			// cache for future instant loads
			chatStore.threadCache.set(threadData)
			chatStore.threadCache.setMessages(threadId, messagesPage, messagesPage.length < 120)
		}

		thread = threadData
		chatStore.activeThread = threadData

		toolTracker.clear()
		messageTree.clear()
		messageSkip = messagesPage.length
		// more messages exist if we got a full page (limit is 120)
		hasMoreMessages = messagesPage.length >= 120
		ingestMessages(messagesPage)

		const preferredLeaf = threadData.current_message_id
		if (preferredLeaf && messageTree.has(preferredLeaf)) {
			currentLeafId = preferredLeaf
		} else if (messageTree.size > 0) {
			let latest: ApiMessage | null = null
			for (const msg of messageTree.values()) {
				if (!latest) {
					latest = msg
					continue
				}
				if (getMessageCreatedAt(msg).getTime() >= getMessageCreatedAt(latest).getTime()) {
					latest = msg
				}
			}
			currentLeafId = latest?.id ?? null
		} else {
			currentLeafId = null
		}

		await fetchToolEventsForThread(
			threadId,
			Array.from(messageTree.values())
				.filter((m) => m.type === 'assistant')
				.map((m) => m.id)
		)
		rebuildRunBlocks()
		return true
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// streaming
	// ─────────────────────────────────────────────────────────────────────────────
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
			parentId: assistantParentId,
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
					streamingLeafId = msg.id
					if (viewingStreamingBranch) {
						currentLeafId = msg.id
					}
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

						const isNewStreamingMessage =
							!streamingAssistant || streamingAssistant.messageId !== messageId
						if (isNewStreamingMessage) {
							hapticFeedback()
							const runId = typeof env.run_id === 'string' ? env.run_id : null
							streamingAssistant = {
								runId,
								messageId,
								content: '',
								timestamp: new SvelteDate(),
								senderAgentId: selectedAgent.id,
								toolCalls: [],
							}
							// insert placeholder into tree so branch nav works immediately
							if (!messageTree.has(messageId)) {
								const now = new SvelteDate().toISOString()
								messageTree.set(messageId, {
									id: messageId,
									thread_id: opts.threadId,
									parent_id: assistantParentId,
									type: 'assistant',
									content: [],
									tool_calls: [],
									metadata_: runId ? { run_id: runId } : undefined,
									sender_agent_id: selectedAgent.id,
									sender_user_id: null,
									created_at: now,
									updated_at: now,
								} satisfies ApiMessage)
							}
							streamingLeafId = messageId
						}
						const streaming = streamingAssistant
						if (!streaming) break

						if (chunkText) streaming.content += chunkText

						// only force rerenders/remounts when tool state changes
						let toolCallsChanged = false
						if (Array.isArray(toolCalls)) {
							const prev = streaming.toolCalls
							const prevSig = prev
								.map((tc) => `${tc.id}:${tc.name}:${JSON.stringify(tc.arguments)}`)
								.join('|')
							const next = upsertToolCalls(prev, toolCalls)
							const nextSig = next
								.map((tc) => `${tc.id}:${tc.name}:${JSON.stringify(tc.arguments)}`)
								.join('|')
							toolCallsChanged = prevSig !== nextSig
							streaming.toolCalls = next
							if (toolCallsChanged) {
								for (const tc of streaming.toolCalls)
									toolTracker.registerToolCall(tc)
								toolTick++
							}
						}

						// only rebuild blocks when structure changes
						if (isNewStreamingMessage || toolCallsChanged) {
							rebuildRunBlocks()
						}

						if (isDone) {
							const content = streaming.content.trim()
							const now = new SvelteDate().toISOString()
							const finalized = {
								id: streaming.messageId,
								thread_id: opts.threadId,
								parent_id: assistantParentId,
								type: 'assistant',
								content: content ? [{ type: 'text', text: content }] : [],
								tool_calls: streaming.toolCalls.map((tc) => ({
									id: tc.id,
									name: tc.name,
									arguments: tc.arguments,
								})),
								metadata_: streaming.runId
									? { run_id: streaming.runId }
									: undefined,
								sender_agent_id: streaming.senderAgentId,
								sender_user_id: null,
								created_at: now,
								updated_at: now,
							} satisfies ApiMessage
							messageTree.set(finalized.id, finalized)
							streamingLeafId = finalized.id
							if (viewingStreamingBranch) {
								currentLeafId = finalized.id
							}
							// update parent chain for next message in this run
							assistantParentId = finalized.id
							streamingAssistantParentId = finalized.id

							// if this message had tool calls, the agent will continue after
							// tool execution — keep a skeleton so the pulsing ball renders
							// during the gap before the next assistant message streams
							if (streaming.toolCalls.length > 0) {
								streamingAssistant = {
									runId: streaming.runId,
									messageId: `pending-next-${opts.runId}`,
									content: '',
									timestamp: new SvelteDate(),
									senderAgentId: streaming.senderAgentId,
									toolCalls: [],
								}
							} else {
								streamingAssistant = null
							}
							rebuildRunBlocks()
						}
					}
					break
				}
			}
		}
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// user actions
	// ─────────────────────────────────────────────────────────────────────────────
	async function handleSendMessage(content: string) {
		const trimmed = content.trim()
		if (!trimmed) return
		if (!thread) return
		const runBaseMessage = trimmed
		if (!selectedAgent) {
			runError = true
			lastRunInput = runBaseMessage
			optimisticUserMessage = { content: runBaseMessage, timestamp: new SvelteDate() }
			return
		}
		runError = false
		lastRunInput = runBaseMessage
		inputValue = ''
		optimisticUserMessage = { content: runBaseMessage, timestamp: new SvelteDate() }
		const shouldAutoScroll = scrollContainer ? computeIsAtBottom(scrollContainer) : true
		isGenerating = true
		streamingAssistant = null
		viewingStreamingBranch = true
		streamingLeafId = null
		streamingAssistant = {
			runId: null,
			messageId: `pending-${activeRun + 1}`,
			content: '',
			timestamp: new SvelteDate(),
			senderAgentId: selectedAgent.id,
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
				agentId: selectedAgent.id,
				input: runBaseMessage,
				runId,
				parentId: currentLeafId,
			})
			if (runId !== activeRun) return
			runError = false
			optimisticUserMessage = null
			streamingAssistant = null
			rebuildRunBlocks()
		} catch (e) {
			console.error('failed to run thread', e)
			runError = true
			optimisticUserMessage = null
			streamingAssistant = null
			rebuildRunBlocks()
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	async function handleRegenerateMessage(parentId: string | null = null) {
		if (!thread) return
		if (!selectedAgent.id) return
		runError = false
		isGenerating = true
		viewingStreamingBranch = true
		streamingLeafId = null

		const resolvedParent = parentId ?? currentLeafId
		streamingAssistantParentId = resolvedParent

		// switch view to parent so old response leaves the visible branch
		if (resolvedParent) currentLeafId = resolvedParent

		streamingAssistant = {
			runId: null,
			messageId: `pending-${activeRun + 1}`,
			content: '',
			timestamp: new SvelteDate(),
			senderAgentId: selectedAgent.id,
			toolCalls: [],
		}
		const runId = ++activeRun
		rebuildRunBlocks()

		try {
			await runThreadStream({
				threadId: thread.id,
				agentId: selectedAgent.id,
				input: optimisticUserMessage ? lastRunInput : null,
				runId,
				parentId: resolvedParent,
			})
			if (runId !== activeRun) return
			runError = false
			optimisticUserMessage = null
			streamingAssistant = null
			streamingAssistantParentId = null
			rebuildRunBlocks()
		} catch (e) {
			console.error('failed to retry run', e)
			runError = true
			streamingAssistant = null
			streamingAssistantParentId = null
			rebuildRunBlocks()
		} finally {
			if (runId === activeRun) isGenerating = false
		}
	}

	function handleStopGeneration() {
		runAbortController?.abort()
		activeRun++
		isGenerating = false
		viewingStreamingBranch = true
		streamingLeafId = null
		optimisticUserMessage = null
		streamingAssistant = null
		streamingAssistantParentId = null
		rebuildRunBlocks()
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

		const { data: newMessage, error } = await apiClient().POST(
			'/v1/threads/{thread_id}/messages',
			{
				params: { path: { thread_id: thread.id } },
				body,
			}
		)

		if (error || !newMessage) {
			console.error('failed to create edited message', error)
			return
		}

		messageTree.set(newMessage.id, newMessage)
		currentLeafId = newMessage.id
		rebuildRunBlocks()

		await handleRegenerateMessage(newMessage.id)
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// delete functionality
	// ─────────────────────────────────────────────────────────────────────────────
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

		const { response, error } = await apiClient().DELETE(
			'/v1/threads/{thread_id}/messages/{message_id}',
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

	// ─────────────────────────────────────────────────────────────────────────────
	// thread loading effect setup
	// ─────────────────────────────────────────────────────────────────────────────
	function setThread(t: Thread | null) {
		thread = t
		chatStore.activeThread = t
	}

	function clearThread() {
		thread = null
		chatStore.activeThread = null
		messageTree.clear()
		currentLeafId = null
		isThreadLoading = false
		hasLoadedBranch = false
		// clear run state to prevent leaking to other chats
		runError = false
		optimisticUserMessage = null
		streamingAssistant = null
		streamingAssistantParentId = null
		viewingStreamingBranch = true
		streamingLeafId = null
		lastRunInput = ''
		runBlocks = []
		// clear tool event tracking for previous thread
		fetchedToolEventMessageIds.clear()
		toolEventsPendingIds.clear()
		toolTracker.clear()
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// tool event subscription
	// ─────────────────────────────────────────────────────────────────────────────
	function subscribeToToolEvents(threadId: string): () => void {
		return eventStreamClient.subscribe((msg) => {
			if (!msg || typeof msg !== 'object') return
			const ev = msg as StreamEvent
			if (!ev.type || typeof ev.type !== 'string') return
			if (!ev.type.startsWith('tool.')) return
			if (ev.thread_id !== threadId) return
			const toolEv = parseToolEvent({
				id: ev.id,
				type: ev.type,
				data: (ev.data ?? {}) as Record<string, unknown>,
				created_at: ev.created_at ?? undefined,
				message_id: ev.message_id ?? undefined,
			})
			if (!toolEv) return
			toolTracker.processEvent(toolEv)
			toolTick++
		})
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// return public interface
	// ─────────────────────────────────────────────────────────────────────────────
	return {
		// state (getters for reactive access)
		get inputValue() {
			return inputValue
		},
		set inputValue(v: string) {
			inputValue = v
		},
		get isGenerating() {
			return isGenerating
		},
		get optimisticUserMessage() {
			return optimisticUserMessage
		},
		get streamingAssistant() {
			return streamingAssistant
		},
		get streamingAssistantParentId() {
			return streamingAssistantParentId
		},
		get runError() {
			return runError
		},
		get runBlocks() {
			return runBlocks
		},
		get thread() {
			return thread
		},
		get isThreadLoading() {
			return isThreadLoading
		},
		set isThreadLoading(v: boolean) {
			isThreadLoading = v
		},
		get hasLoadedBranch() {
			return hasLoadedBranch
		},
		set hasLoadedBranch(v: boolean) {
			hasLoadedBranch = v
		},
		get messageTree() {
			return messageTree
		},
		get messageChildren() {
			return messageChildren
		},
		get currentLeafId() {
			return currentLeafId
		},
		get messages() {
			return messages
		},
		get hasMoreMessages() {
			return hasMoreMessages
		},
		get isLoadingOlderMessages() {
			return isLoadingOlderMessages
		},
		get scrollContainer() {
			return scrollContainer
		},
		set scrollContainer(v: HTMLElement | null) {
			scrollContainer = v
		},
		get inputOverlay() {
			return inputOverlay
		},
		set inputOverlay(v: HTMLElement | null) {
			inputOverlay = v
		},
		get autoScroll() {
			return autoScroll
		},
		set autoScroll(v: boolean) {
			autoScroll = v
		},
		get initialScrollDone() {
			return initialScrollDone
		},
		set initialScrollDone(v: boolean) {
			initialScrollDone = v
		},
		get lastThreadId() {
			return lastThreadId
		},
		set lastThreadId(v: string | null) {
			lastThreadId = v
		},
		get inputOverlayHeight() {
			return inputOverlayHeight
		},
		set inputOverlayHeight(v: number) {
			inputOverlayHeight = v
		},
		get toolTracker() {
			return toolTracker
		},
		getToolExecution,
		get toolTick() {
			return toolTick
		},
		get confirmDeleteMessage() {
			return confirmDeleteMessage
		},
		set confirmDeleteMessage(v: { id: string; preview: string } | null) {
			confirmDeleteMessage = v
		},
		get isDeletingMessage() {
			return isDeletingMessage
		},
		set isDeletingMessage(v: boolean) {
			isDeletingMessage = v
		},
		get deleteMessageError() {
			return deleteMessageError
		},
		set deleteMessageError(v: string | null) {
			deleteMessageError = v
		},

		// derived
		get isTemporaryChat() {
			return isTemporaryChat
		},
		get showThreadLoader() {
			return showThreadLoader
		},
		get hasRenderableMessages() {
			return hasRenderableMessages
		},
		get viewingStreamingBranch() {
			return viewingStreamingBranch
		},
		get hasActiveStreamingToolCalls() {
			if (!streamingAssistant) return false
			if (streamingAssistant.toolCalls.length === 0) return false
			return streamingAssistant.toolCalls.some((tc) => {
				const exec = getToolExecution(tc.id)
				return !exec || exec.status === 'pending' || exec.status === 'running'
			})
		},
		get agentNameById() {
			return agentNameById
		},
		get agentAvatarById() {
			return agentAvatarById
		},
		// methods
		rebuildRunBlocks,
		getBlockResponseItems,
		getBlockFirstAssistant,
		blockHasStreamingAssistant,
		findRunUserMessage,
		switchBranch,
		handleScroll,
		scrollToBottom,
		queueScrollToBottom,
		loadTree,
		handleSendMessage,
		handleRegenerateMessage,
		handleStopGeneration,
		handleEditMessage,
		requestDeleteUserMessage,
		deleteUserMessage,
		setThread,
		clearThread,
		subscribeToToolEvents,
		contentPartsToText,
		getMessageCreatedAt,
	}
}

export type ChatState = ReturnType<typeof createChatState>

/**
 * Reactive chat state management using Svelte 5 runes.
 * Encapsulates all chat page state and business logic.
 */

import { eventStreamClient, runChatStream, type StreamEvent } from '$lib/api/streaming'
import type { components } from '$lib/api/types'
import { v1Client } from '$lib/api/v1/client'
import { agentsList } from '$lib/stores/agents'
import { currentUser, setActiveThread, type Thread } from '$lib/stores/session'
import {
	ToolExecutionTracker,
	parseToolCalls,
	parseToolEvent,
	parseToolResult,
	type ToolCall,
} from '$lib/tools'
import { tick } from 'svelte'
import { SvelteDate, SvelteMap, SvelteSet } from 'svelte/reactivity'
import { get } from 'svelte/store'
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
 * Creates the reactive chat state for a thread page.
 * Returns an object with all state and methods needed by the UI.
 */
export function createChatState() {
	// ─────────────────────────────────────────────────────────────────────────────
	// Core state
	// ─────────────────────────────────────────────────────────────────────────────
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let selectedAgent = $state('')
	let optimisticUserMessage = $state<{ content: string; timestamp: Date } | null>(null)
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let streamingAssistantParentId = $state<string | null>(null)
	let runError = $state(false)
	let lastRunInput = $state('')
	let runBlocks = $state<RunBlock[]>([])

	// Thread state
	let thread = $state<Thread | null>(null)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)

	// Message tree (for branching)
	const messageTree = new SvelteMap<string, ApiMessage>()
	let currentLeafId = $state<string | null>(null)

	// Scroll state
	let scrollContainer = $state<HTMLElement | null>(null)
	let inputOverlay = $state<HTMLElement | null>(null)
	let autoScroll = $state(true)
	let initialScrollDone = $state(false)
	let lastThreadId = $state<string | null>(null)
	let inputOverlayHeight = $state(0)
	let scrollQueued = false

	// Tool tracking
	const toolTracker = new ToolExecutionTracker()
	let toolTick = $state(0)

	function getToolExecution(toolCallId: string) {
		if (toolTick < 0) return null
		return toolTracker.getExecution(toolCallId)
	}

	// Delete confirmation
	let confirmDeleteMessage = $state<{ id: string; preview: string } | null>(null)
	let isDeletingMessage = $state(false)
	let deleteMessageError = $state<string | null>(null)

	// Abort controller for streaming
	let runAbortController: AbortController | null = null

	// ─────────────────────────────────────────────────────────────────────────────
	// Derived state
	// ─────────────────────────────────────────────────────────────────────────────
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)
	const showThreadLoader = $derived(isThreadLoading)
	const currentUserId = $derived(get(currentUser)?.id ?? null)

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

	// Reconstruct the active branch from root to currentLeafId
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

	const agentNameById = $derived(new SvelteMap(get(agentsList).map((a) => [a.id, a.name])))
	const agentAvatarById = $derived(
		new SvelteMap(get(agentsList).map((a) => [a.id, a.profile_image_url ?? null]))
	)
	const selectedAgentName = $derived(
		get(agentsList).find((a) => a.id === selectedAgent)?.name ?? 'assistant'
	)

	// ─────────────────────────────────────────────────────────────────────────────
	// Tool call helpers
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
	// Run block management
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

	function blockHasStreamingAssistant(block: RunBlock): boolean {
		return block.items.some((item) => item.kind === 'streaming_assistant')
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// Branch navigation
	// ─────────────────────────────────────────────────────────────────────────────
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

	/**
	 * Find the user message that started a run by walking up from the response root.
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
	// Scroll management
	// ─────────────────────────────────────────────────────────────────────────────
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

	// ─────────────────────────────────────────────────────────────────────────────
	// Data loading
	// ─────────────────────────────────────────────────────────────────────────────
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

	async function loadTree(threadId: string): Promise<boolean> {
		// Load the thread first so we have the current leaf and can render the active branch.
		const { data: threadData, error: threadError } = await v1Client().GET(
			'/threads/{thread_id}',
			{ params: { path: { thread_id: threadId } } }
		)
		if (threadError) {
			console.error('failed to load thread', threadError)
			thread = null
			setActiveThread(null)
			toolTracker.clear()
			messageTree.clear()
			currentLeafId = null
			rebuildRunBlocks()
			return false
		}
		if (!threadData) {
			thread = null
			setActiveThread(null)
			toolTracker.clear()
			messageTree.clear()
			currentLeafId = null
			rebuildRunBlocks()
			return true
		}

		thread = threadData
		setActiveThread(threadData)

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
		const preferredLeaf = threadData.current_message_id
		if (preferredLeaf && messageTree.has(preferredLeaf)) {
			currentLeafId = preferredLeaf
		} else if (msgs.length > 0) {
			const latest = msgs
				.slice()
				.sort((a, b) => getMessageCreatedAt(a).getTime() - getMessageCreatedAt(b).getTime())
				.at(-1)
			currentLeafId = latest?.id ?? null
		} else {
			currentLeafId = null
		}

		await fetchToolEventsForThread(
			threadId,
			msgs.filter((m) => m.type === 'assistant').map((m) => m.id)
		)
		rebuildRunBlocks()
		return true
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// Streaming
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

						const isNewStreamingMessage =
							!streamingAssistant || streamingAssistant.messageId !== messageId
						if (isNewStreamingMessage) {
							streamingAssistant = {
								runId: typeof env.run_id === 'string' ? env.run_id : null,
								messageId,
								content: '',
								timestamp: new SvelteDate(),
								senderAgentId: selectedAgent,
								toolCalls: [],
							}
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
								metadata_: streaming.runId ? { run_id: streaming.runId } : {},
								sender_agent_id: streaming.senderAgentId,
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

	// ─────────────────────────────────────────────────────────────────────────────
	// User actions
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
		optimisticUserMessage = { content: runBaseMessage, timestamp: new SvelteDate() }
		const shouldAutoScroll = scrollContainer ? computeIsAtBottom(scrollContainer) : true
		isGenerating = true
		streamingAssistant = {
			runId: null,
			messageId: `pending-${activeRun + 1}`,
			content: '',
			timestamp: new SvelteDate(),
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

	async function handleRegenerateMessage(parentId: string | null = null) {
		if (!thread) return
		if (!selectedAgent) return
		runError = false
		isGenerating = true

		streamingAssistantParentId = parentId ?? currentLeafId
		streamingAssistant = {
			runId: null,
			messageId: `pending-${activeRun + 1}`,
			content: '',
			timestamp: new SvelteDate(),
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

	// ─────────────────────────────────────────────────────────────────────────────
	// Delete functionality
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

	// ─────────────────────────────────────────────────────────────────────────────
	// Thread loading effect setup
	// ─────────────────────────────────────────────────────────────────────────────
	function setThread(t: Thread | null) {
		thread = t
		setActiveThread(t)
	}

	function clearThread() {
		thread = null
		setActiveThread(null)
		messageTree.clear()
		currentLeafId = null
		isThreadLoading = false
		hasLoadedBranch = false
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// Tool event subscription
	// ─────────────────────────────────────────────────────────────────────────────
	function subscribeToToolEvents(threadId: string): () => void {
		return eventStreamClient.subscribe((msg) => {
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
	}

	// ─────────────────────────────────────────────────────────────────────────────
	// Return public interface
	// ─────────────────────────────────────────────────────────────────────────────
	return {
		// State (getters for reactive access)
		get inputValue() {
			return inputValue
		},
		set inputValue(v: string) {
			inputValue = v
		},
		get isGenerating() {
			return isGenerating
		},
		get selectedAgent() {
			return selectedAgent
		},
		set selectedAgent(v: string) {
			selectedAgent = v
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

		// Derived
		get isTemporaryChat() {
			return isTemporaryChat
		},
		get showThreadLoader() {
			return showThreadLoader
		},
		get hasRenderableMessages() {
			return hasRenderableMessages
		},
		get agentNameById() {
			return agentNameById
		},
		get agentAvatarById() {
			return agentAvatarById
		},
		get selectedAgentName() {
			return selectedAgentName
		},

		// Methods
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
		handleCopyMessage,
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

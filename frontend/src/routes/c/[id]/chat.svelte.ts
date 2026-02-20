/**
 * reactive chat state management using Svelte 5 runes.
 * coordinates the modules in $lib/chat/ via a ChatContext object.
 */

import type { ChatStreamDelta } from '$lib/api/streaming'
import {
	blockHasStreamingAssistant,
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	contentPartsToText,
	getBlockFirstAssistant,
	getBlockResponseItems,
	getMessageCreatedAt,
	type ApiMessage,
	type ChatContext,
	type RunBlock,
	type StreamingAssistantState,
} from '$lib/chat'
import {
	loadOlderMessages as _loadOlderMessages,
	loadTree as _loadTree,
} from '$lib/chat/dataLoader'
import {
	sendTypingEvent as _sendTypingEvent,
	subscribeToChatEvents,
} from '$lib/chat/eventSubscriptions'
import { resumeCreateAndRun as _resumeCreateAndRun } from '$lib/chat/streamProcessor'
import {
	findRunUserMessage as _findRunUserMessage,
	switchBranch as _switchBranch,
} from '$lib/chat/treeNavigation'
import {
	deleteUserMessage as _deleteUserMessage,
	handleEditMessage as _handleEditMessage,
	handleRegenerateMessage as _handleRegenerateMessage,
	handleSendMessage as _handleSendMessage,
	handleStopGeneration as _handleStopGeneration,
	requestDeleteUserMessage as _requestDeleteUserMessage,
} from '$lib/chat/userActions'
import { agents } from '$lib/stores/agents.svelte'
import { chat as chatStore, type Thread } from '$lib/stores/chat.svelte'
import { session } from '$lib/stores/session.svelte'
import { ToolExecutionTracker } from '$lib/tools'
import { tick } from 'svelte'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'

export type { ApiMessage }

// re-export types for backward compatibility
export type { RunBlock, RunItem, StreamingAssistantState } from '$lib/chat'

/**
 * creates the reactive chat state for a thread page.
 * returns an object with all state and methods needed by the UI.
 */
export function createChatState() {
	// ── core state ───────────────────────────────────────────────────────
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let optimisticUserMessage = $state<{ content: string; timestamp: Date } | null>(null)
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let streamingAssistantParentId = $state<string | null>(null)
	let viewingStreamingBranch = $state(true)
	let streamingLeafId = $state<string | null>(null)
	let lastRunInput = $state('')
	let runBlocks = $state<RunBlock[]>([])

	// ── thread state ─────────────────────────────────────────────────────
	let thread = $state<Thread | null>(null)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)

	// ── message paging (latest-first from backend) ───────────────────────
	let messageSkip = $state(0)
	let hasMoreMessages = $state(true)
	let isLoadingOlderMessages = $state(false)

	// ── message tree (for branching) ─────────────────────────────────────
	const messageTree = new SvelteMap<string, ApiMessage>()
	let currentLeafId = $state<string | null>(null)

	// ── scroll state ─────────────────────────────────────────────────────
	let scrollContainer = $state<HTMLElement | null>(null)
	let inputOverlay = $state<HTMLElement | null>(null)
	let autoScroll = $state(true)
	let initialScrollDone = $state(false)
	let lastThreadId = $state<string | null>(null)
	let inputOverlayHeight = $state(0)
	let scrollQueued = false

	// ── tool tracking ────────────────────────────────────────────────────
	const toolTracker = new ToolExecutionTracker()
	let toolTick = $state(0)
	const fetchedToolEventMessageIds = new SvelteSet<string>()
	const toolEventsPendingIds = new SvelteSet<string>()
	let toolEventsInFlight = $state(false)

	function getToolExecution(toolCallId: string) {
		if (toolTick < 0) return null
		return toolTracker.getExecution(toolCallId)
	}

	// ── delete confirmation ──────────────────────────────────────────────
	let confirmDeleteMessage = $state<{ id: string; preview: string } | null>(null)
	let isDeletingMessage = $state(false)
	let deleteMessageError = $state<string | null>(null)

	// ── typing indicators (other users typing in this thread) ────────────
	const typingUsers = new SvelteSet<string>()

	// ── active agent runs ────────────────────────────────────────────────
	const activeAgentRuns = new SvelteMap<
		string,
		{ threadId: string; runId: string; agentId: string }
	>()

	// ── abort controller for streaming ───────────────────────────────────
	let runAbortController: AbortController | null = null

	// ── derived state ────────────────────────────────────────────────────
	const isTemporaryChat = $derived(thread?.is_temporary ?? false)
	const showThreadLoader = $derived(isThreadLoading)
	const currentUserId = $derived(session.currentUser?.id ?? null)

	const messageChildren = $derived.by(() => buildMessageChildren(messageTree.values()))

	// reconstruct the active branch from root to currentLeafId
	const messages = $derived.by(() => {
		if (!currentLeafId) return []
		const branch: ApiMessage[] = []
		const visited = new SvelteSet<string>()
		let curr: string | null = currentLeafId
		while (curr) {
			if (visited.has(curr)) break
			visited.add(curr)
			const msg = messageTree.get(curr)
			if (!msg) break
			branch.unshift(msg)
			curr = msg.parent_id ?? null
		}
		return branch
	})

	const hasRenderableMessages = $derived(
		runBlocks.some((b) => b.items.length > 0) || optimisticUserMessage !== null
	)

	const agentNameById = $derived(buildAgentLookup(agents.list, (a) => a.name))
	const agentAvatarById = $derived(
		buildAgentLookup(agents.list, (a) => a.profile_image_url ?? null)
	)

	// ── run block management ─────────────────────────────────────────────
	function rebuildRunBlocks(): void {
		const result = buildRunBlocks({
			messages,
			userId: currentUserId,
			streamingAssistant,
			optimisticUserMessage,
			viewingStreamingBranch,
		})

		// apply side effects: register tool calls and results
		for (const tc of result.toolCalls) toolTracker.registerToolCall(tc)
		for (const tr of result.toolResults) toolTracker.registerResult(tr)
		if (result.toolCalls.length > 0 || result.toolResults.length > 0) toolTick++

		runBlocks = result.blocks
	}

	// ── scroll management ────────────────────────────────────────────────
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
			void _loadOlderMessages(threadId, ctx)
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

	// ── thread lifecycle ─────────────────────────────────────────────────
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

	// ── ChatContext — bridges reactive $state to extracted modules ────────
	const ctx: ChatContext = {
		get thread() {
			return thread
		},
		set thread(v) {
			thread = v
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
		set currentLeafId(v) {
			currentLeafId = v
		},
		get messages() {
			return messages
		},
		get isGenerating() {
			return isGenerating
		},
		set isGenerating(v) {
			isGenerating = v
		},
		get activeRun() {
			return activeRun
		},
		set activeRun(v) {
			activeRun = v
		},
		get streamingAssistant() {
			return streamingAssistant
		},
		set streamingAssistant(v) {
			streamingAssistant = v
		},
		get streamingAssistantParentId() {
			return streamingAssistantParentId
		},
		set streamingAssistantParentId(v) {
			streamingAssistantParentId = v
		},
		get streamingLeafId() {
			return streamingLeafId
		},
		set streamingLeafId(v) {
			streamingLeafId = v
		},
		get viewingStreamingBranch() {
			return viewingStreamingBranch
		},
		set viewingStreamingBranch(v) {
			viewingStreamingBranch = v
		},
		get optimisticUserMessage() {
			return optimisticUserMessage
		},
		set optimisticUserMessage(v) {
			optimisticUserMessage = v
		},
		get lastRunInput() {
			return lastRunInput
		},
		set lastRunInput(v) {
			lastRunInput = v
		},
		get inputValue() {
			return inputValue
		},
		set inputValue(v) {
			inputValue = v
		},
		get runAbortController() {
			return runAbortController
		},
		set runAbortController(v) {
			runAbortController = v
		},
		get messageSkip() {
			return messageSkip
		},
		set messageSkip(v) {
			messageSkip = v
		},
		get hasMoreMessages() {
			return hasMoreMessages
		},
		set hasMoreMessages(v) {
			hasMoreMessages = v
		},
		get isLoadingOlderMessages() {
			return isLoadingOlderMessages
		},
		set isLoadingOlderMessages(v) {
			isLoadingOlderMessages = v
		},
		get scrollContainer() {
			return scrollContainer
		},
		get autoScroll() {
			return autoScroll
		},
		set autoScroll(v) {
			autoScroll = v
		},
		get toolTracker() {
			return toolTracker
		},
		get toolTick() {
			return toolTick
		},
		set toolTick(v) {
			toolTick = v
		},
		get fetchedToolEventMessageIds() {
			return fetchedToolEventMessageIds
		},
		get toolEventsPendingIds() {
			return toolEventsPendingIds
		},
		get toolEventsInFlight() {
			return toolEventsInFlight
		},
		set toolEventsInFlight(v) {
			toolEventsInFlight = v
		},
		get confirmDeleteMessage() {
			return confirmDeleteMessage
		},
		set confirmDeleteMessage(v) {
			confirmDeleteMessage = v
		},
		get isDeletingMessage() {
			return isDeletingMessage
		},
		set isDeletingMessage(v) {
			isDeletingMessage = v
		},
		get deleteMessageError() {
			return deleteMessageError
		},
		set deleteMessageError(v) {
			deleteMessageError = v
		},
		get typingUsers() {
			return typingUsers
		},
		get activeAgentRuns() {
			return activeAgentRuns
		},
		get isTemporaryChat() {
			return isTemporaryChat
		},
		get currentUserId() {
			return currentUserId
		},
		incrementActiveRun() {
			return ++activeRun
		},
		rebuildRunBlocks,
		queueScrollToBottom,
	}

	// ── public interface ─────────────────────────────────────────────────
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

		// methods (delegating to $lib/chat modules)
		rebuildRunBlocks,
		getBlockResponseItems,
		getBlockFirstAssistant,
		blockHasStreamingAssistant,
		findRunUserMessage: (block: RunBlock) => _findRunUserMessage(block, ctx),
		switchBranch: (messageId: string, direction: 'prev' | 'next') =>
			_switchBranch(messageId, direction, ctx),
		handleScroll,
		scrollToBottom,
		queueScrollToBottom,
		loadTree: (threadId: string) => _loadTree(threadId, ctx),
		handleSendMessage: (content: string) => _handleSendMessage(content, ctx),
		handleRegenerateMessage: (parentId?: string | null) =>
			_handleRegenerateMessage(parentId ?? null, ctx),
		handleStopGeneration: () => _handleStopGeneration(ctx),
		handleEditMessage: (messageId: string) => _handleEditMessage(messageId, ctx),
		resumeCreateAndRun: (
			stream: AsyncGenerator<ChatStreamDelta, void, unknown>,
			threadId: string
		) => _resumeCreateAndRun(stream, threadId, ctx),
		requestDeleteUserMessage: (messageId: string) => _requestDeleteUserMessage(messageId, ctx),
		deleteUserMessage: (messageId: string) => _deleteUserMessage(messageId, ctx),
		setThread,
		clearThread,
		subscribeToChatEvents: (threadId: string) => subscribeToChatEvents(threadId, ctx),
		sendTypingEvent: _sendTypingEvent,
		get typingUsers() {
			return typingUsers
		},
		get activeAgentRuns() {
			return activeAgentRuns
		},
		contentPartsToText,
		getMessageCreatedAt,
	}
}

export type ChatState = ReturnType<typeof createChatState>

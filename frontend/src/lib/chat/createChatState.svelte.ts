/**
 * reactive chat state factory using Svelte 5 runes.
 * creates a single unified state object that serves as both:
 * - ChatContext for extracted $lib/chat/ module functions
 * - ChatState for the page UI
 *
 * this eliminates the double-proxy pattern that existed before.
 */

import { agents } from '$lib/stores/agents.svelte'
import { chat as chatStore, type Thread } from '$lib/stores/chat.svelte'
import { session } from '$lib/stores/session.svelte'
import { ToolExecutionTracker } from '$lib/tools'
import { tick } from 'svelte'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { loadOlderMessages, loadTree } from './dataLoader'
import { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions'
import {
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	type ApiMessage,
	type RunBlock,
	type StreamingAssistantState,
} from './helpers'
import { resumeCreateAndRun } from './streamProcessor'
import { findRunUserMessage, switchBranch } from './treeNavigation'
import type { ChatState } from './types'
import {
	deleteUserMessage,
	handleRegenerateMessage,
	handleSaveAsCopyMessage,
	handleSaveEditMessage,
	handleSendMessage,
	handleStopGeneration,
	requestDeleteUserMessage,
} from './userActions'

/**
 * creates the reactive chat state for a thread page.
 * returns a single ChatState object used by both the page and library modules.
 */
export function createChatState(): ChatState {
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
	const fetchedToolEventMessageIds = new SvelteSet<string>()
	const toolEventsPendingIds = new SvelteSet<string>()
	let toolEventsInFlight = $state(false)

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

		runBlocks = result.blocks
	}

	// ── scroll management ────────────────────────────────────────────────
	// position-based auto-scroll: every scroll event checks if we're at the
	// bottom. if yes → autoScroll stays/becomes true. if no → false.
	function handleScroll() {
		if (!scrollContainer) return
		autoScroll = computeIsAtBottom(scrollContainer)

		// avoid runaway paging during initial mount/auto-scroll.
		// initialScrollDone is set once we have loaded and pinned to bottom.
		if (!initialScrollDone) return
		if (scrollContainer.scrollTop <= 80) {
			const threadId = thread?.id
			if (!threadId) return
			if (!hasMoreMessages) return
			if (isLoadingOlderMessages) return
			void loadOlderMessages(threadId, state)
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
			if (!autoScroll) return
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

	// ── unified state object ─────────────────────────────────────────────
	// single object serving both as ChatContext for module functions and
	// ChatState for the page UI. eliminates the double-proxy pattern.
	const state: ChatState = {
		// ── thread ───────────────────────────────────────────────────────
		get thread() {
			return thread
		},
		set thread(v) {
			thread = v
		},

		// ── message tree ─────────────────────────────────────────────────
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

		// ── streaming ────────────────────────────────────────────────────
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

		// ── paging ───────────────────────────────────────────────────────
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

		// ── scroll ───────────────────────────────────────────────────────
		get scrollContainer() {
			return scrollContainer
		},
		set scrollContainer(v) {
			scrollContainer = v
		},
		get autoScroll() {
			return autoScroll
		},
		set autoScroll(v) {
			autoScroll = v
		},

		// ── tools ────────────────────────────────────────────────────────
		get toolTracker() {
			return toolTracker
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

		// ── delete ───────────────────────────────────────────────────────
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

		// ── realtime ─────────────────────────────────────────────────────
		get typingUsers() {
			return typingUsers
		},
		get activeAgentRuns() {
			return activeAgentRuns
		},

		// ── derived ──────────────────────────────────────────────────────
		get isTemporaryChat() {
			return isTemporaryChat
		},
		get currentUserId() {
			return currentUserId
		},
		get runBlocks() {
			return runBlocks
		},
		get showThreadLoader() {
			return showThreadLoader
		},
		get hasRenderableMessages() {
			return hasRenderableMessages
		},
		get hasActiveStreamingToolCalls() {
			if (!streamingAssistant) return false
			if (streamingAssistant.toolCalls.length === 0) return false
			return streamingAssistant.toolCalls.some((tc) => toolTracker.isActive(tc.id))
		},
		get agentNameById() {
			return agentNameById
		},
		get agentAvatarById() {
			return agentAvatarById
		},

		// ── page-specific state ──────────────────────────────────────────
		get isThreadLoading() {
			return isThreadLoading
		},
		set isThreadLoading(v) {
			isThreadLoading = v
		},
		get hasLoadedBranch() {
			return hasLoadedBranch
		},
		set hasLoadedBranch(v) {
			hasLoadedBranch = v
		},
		get inputOverlay() {
			return inputOverlay
		},
		set inputOverlay(v) {
			inputOverlay = v
		},
		get initialScrollDone() {
			return initialScrollDone
		},
		set initialScrollDone(v) {
			initialScrollDone = v
		},
		get lastThreadId() {
			return lastThreadId
		},
		set lastThreadId(v) {
			lastThreadId = v
		},
		get inputOverlayHeight() {
			return inputOverlayHeight
		},
		set inputOverlayHeight(v) {
			inputOverlayHeight = v
		},

		// ── coordinator methods ──────────────────────────────────────────
		incrementActiveRun() {
			return ++activeRun
		},
		rebuildRunBlocks,
		queueScrollToBottom,
		handleScroll,
		scrollToBottom,
		setThread,
		clearThread,
		getToolExecution(toolCallId: string) {
			return toolTracker.get(toolCallId)
		},

		// ── delegated to $lib/chat modules ───────────────────────────────
		loadTree: (threadId) => loadTree(threadId, state),
		handleSendMessage: (content) => handleSendMessage(content, state),
		handleRegenerateMessage: (parentId, prompt) =>
			handleRegenerateMessage(parentId ?? null, state, prompt),
		handleStopGeneration: () => handleStopGeneration(state),
		handleSaveEditMessage: (messageId, newContent) =>
			handleSaveEditMessage(messageId, newContent, state),
		handleSaveAsCopyMessage: (messageId, newContent) =>
			handleSaveAsCopyMessage(messageId, newContent, state),
		resumeCreateAndRun: (stream, threadId) => resumeCreateAndRun(stream, threadId, state),
		requestDeleteUserMessage: (messageId) => requestDeleteUserMessage(messageId, state),
		deleteUserMessage: (messageId) => deleteUserMessage(messageId, state),
		switchBranch: (messageId, direction) => switchBranch(messageId, direction, state),
		findRunUserMessage: (block) => findRunUserMessage(block, state),
		subscribeToChatEvents: (threadId) => subscribeToChatEvents(threadId, state),
		sendTypingEvent,
	}

	return state
}

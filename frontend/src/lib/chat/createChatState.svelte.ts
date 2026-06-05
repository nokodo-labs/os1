/**
 * reactive chat state factory using Svelte 5 runes.
 * creates a single unified state object that serves as both:
 * - ChatContext for extracted $lib/chat/ module functions
 * - ChatState for the page UI
 *
 * this eliminates the double-proxy pattern that existed before.
 */

import { activeRunsStore } from '$lib/stores/activeRuns.svelte'
import { agents } from '$lib/stores/agents.svelte'
import { chat as chatStore, type Thread } from '$lib/stores/chat.svelte'
import { session } from '$lib/stores/session.svelte'
import { ToolExecutionTracker } from '$lib/tools'
import { tick } from 'svelte'
import { SvelteDate, SvelteMap, SvelteSet } from 'svelte/reactivity'
import { loadOlderMessages, loadTree } from './dataLoader'
import { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions.svelte'
import {
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	type RunBlock,
	type StreamingAssistantState,
} from './helpers'
import { reduceRunActivityEvent, runActivityKey } from './runActivities'
import {
	dropSteering as dropSteeringApi,
	SteeringRunNotFoundError,
	steerRun as steerRunApi,
} from './steering'
import { resumeCreateAndRun } from './streamProcessor'
import { findRunUserMessage, switchBranch } from './treeNavigation'
import type {
	ApiCitation,
	ApiMessage,
	ChatState,
	OptimisticUserMessage,
	QueuedSteeringMessage,
	RunActivityEvent,
	RunActivityState,
} from './types'
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
	// core state
	let inputValue = $state('')
	let isGenerating = $state(false)
	let activeRun = 0
	let optimisticUserMessage = $state<OptimisticUserMessage | null>(null)
	const queuedSteeringById = new SvelteMap<string, QueuedSteeringMessage>()
	const queuedSteeringServerIdsByClientId = new SvelteMap<string, string>()
	const steeringParentOverrides = new SvelteMap<string, string>()
	let pendingSteeringFlushInFlight = false
	let streamingAssistant = $state<StreamingAssistantState | null>(null)
	let streamingAssistantParentId = $state<string | null>(null)
	let viewingStreamingBranch = $state(true)
	let streamingLeafId = $state<string | null>(null)
	let lastRunInput = $state('')
	let runBlocks = $state<RunBlock[]>([])

	// thread state (activeThread in chatStore is the source of truth)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)
	let targetThreadId = $state<string | null>(null)
	let threadLoadToken = 0

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
	let scrollRequestedWhileQueued = false

	// tool tracking
	const toolTracker = new ToolExecutionTracker()
	const fetchedEventMessageIds = new SvelteSet<string>()
	const eventMessageIdsPending = new SvelteSet<string>()
	let eventsInFlight = $state(false)
	const runActivities = new SvelteMap<string, RunActivityState>()

	// citation sources - message-scoped map populated from citation.sources WS events.
	// keyed by assistant message_id so each message has its own citation set.
	const citationSources = new SvelteMap<string, ApiCitation[]>()
	// run-level accumulator: citations are cumulative across iterations within
	// a single run. flushed into citationSources per-message on stream start.
	let runCitationAccumulator: ApiCitation[] = []
	// last finalized assistant message id - fallback target for late WS citation
	// events that arrive after the SSE stream has already finalized the message.
	let citationTargetMessageId: string | null = null

	// typing indicators (other users typing in this thread)
	const typingUsers = new SvelteSet<string>()

	// abort controller for streaming
	let runAbortController: AbortController | null = null

	// derived state
	const isTemporaryChat = $derived(chatStore.activeThread?.is_temporary ?? false)
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

	const queuedSteeringMessages = $derived.by(() =>
		Array.from(queuedSteeringById.values()).sort(
			(a, b) => a.createdAt.getTime() - b.createdAt.getTime()
		)
	)

	const hasRenderableMessages = $derived(
		runBlocks.some((b) => b.items.length > 0) ||
			optimisticUserMessage !== null ||
			queuedSteeringMessages.length > 0
	)

	const agentNameById = $derived(buildAgentLookup(agents.list, (a) => a.name))
	const agentAvatarById = $derived(
		buildAgentLookup(agents.list, (a) => a.profile_image_url ?? null)
	)

	// run block management
	function rebuildRunBlocks(): void {
		const result = buildRunBlocks({
			messages,
			userId: currentUserId,
			streamingAssistant,
			optimisticUserMessage,
			viewingStreamingBranch,
			runActivities: Array.from(runActivities.values()),
		})

		// apply side effects: register tool calls and results
		for (const tc of result.toolCalls) toolTracker.registerToolCall(tc)
		for (const tr of result.toolResults) toolTracker.registerResult(tr)

		runBlocks = result.blocks
	}

	function stageQueuedSteeringMessage(message: QueuedSteeringMessage): void {
		queuedSteeringById.set(message.id, message)
	}

	function removeQueuedSteeringMessage(messageId: string): void {
		queuedSteeringById.delete(messageId)
		for (const [clientId, serverId] of queuedSteeringServerIdsByClientId) {
			if (clientId === messageId || serverId === messageId) {
				queuedSteeringServerIdsByClientId.delete(clientId)
			}
		}
	}

	/** merge a message-anchored run activity event and refresh visible run blocks. */
	function processRunActivityEvent(event: RunActivityEvent): void {
		const key = runActivityKey(event)
		runActivities.set(key, reduceRunActivityEvent(runActivities.get(key), event))
		rebuildRunBlocks()
	}

	function confirmQueuedSteeringMessage(
		clientSteeringId: string,
		messageId: string,
		runId: string,
		message?: ApiMessage
	): boolean {
		const activeId = queuedSteeringServerIdsByClientId.get(clientSteeringId) ?? clientSteeringId
		const current = queuedSteeringById.get(activeId) ?? queuedSteeringById.get(messageId)
		queuedSteeringServerIdsByClientId.set(clientSteeringId, messageId)
		if (!current) return false

		if (activeId !== messageId) queuedSteeringById.delete(activeId)
		queuedSteeringById.set(messageId, {
			...current,
			id: messageId,
			clientSteeringId,
			runId,
			content: message?.content ?? current.content,
			createdAt: message?.created_at ? new SvelteDate(message.created_at) : current.createdAt,
			message: message ?? current.message,
			deliveryState: 'queued',
			input: undefined,
		})
		return true
	}

	function nextPendingSteeringMessage(runId: string | null): QueuedSteeringMessage | null {
		for (const message of queuedSteeringById.values()) {
			if (message.deliveryState !== 'sending') continue
			if (runId && message.runId && message.runId !== runId) continue
			return message
		}
		return null
	}

	async function flushPendingSteeringMessages(
		runId: string | null,
		parentId: string | null
	): Promise<void> {
		if (pendingSteeringFlushInFlight) return
		pendingSteeringFlushInFlight = true
		let nextParentId = parentId
		try {
			for (;;) {
				const pending = nextPendingSteeringMessage(runId)
				if (!pending) return
				const targetRunId = runId ?? pending.runId
				if (!targetRunId || !pending.input) return

				try {
					const clientSteeringId = pending.clientSteeringId ?? pending.id
					const queued = await steerRunApi(
						targetRunId,
						pending.input,
						nextParentId,
						clientSteeringId
					)
					const activeId =
						queuedSteeringServerIdsByClientId.get(clientSteeringId) ?? pending.id
					const current = queuedSteeringById.get(activeId)
					if (!current) {
						if (queued.state === 'queued') {
							try {
								await dropSteeringApi(targetRunId, queued.messageId)
							} catch (error) {
								console.error(
									'failed to drop removed pending steering message',
									error
								)
							}
						}
						continue
					}

					if (queued.state !== 'queued') {
						removeQueuedSteeringMessage(activeId)
						continue
					}
					confirmQueuedSteeringMessage(clientSteeringId, queued.messageId, targetRunId)
					nextParentId = queued.messageId
				} catch (error) {
					if (error instanceof SteeringRunNotFoundError) {
						activeRunsStore.forgetRun(error.runId)
						for (const queued of [...queuedSteeringById.values()]) {
							if (
								queued.deliveryState === 'sending' &&
								(queued.runId === error.runId || queued.id === pending.id)
							) {
								removeQueuedSteeringMessage(queued.id)
							}
						}
						return
					}
					console.error('failed to flush pending steering message', error)
					return
				}
			}
		} finally {
			pendingSteeringFlushInFlight = false
		}
	}

	function injectedMessage(
		messageId: string,
		message: ApiMessage,
		options?: { runId?: string; parentId?: string | null; createdAt?: string | null }
	): ApiMessage {
		const meta = (message.metadata_ ?? {}) as Record<string, unknown>
		const runId = options?.runId ?? (typeof meta.run_id === 'string' ? meta.run_id : null)
		const metadata: Record<string, unknown> = { ...meta, steering_state: 'injected' }
		if (runId) metadata.run_id = runId
		if (options?.createdAt) metadata.steering_injected_at = options.createdAt
		return {
			...message,
			parent_id: options?.parentId ?? message.parent_id,
			created_at: options?.createdAt ?? message.created_at,
			updated_at: options?.createdAt ?? message.updated_at,
			metadata_: metadata,
			id: messageId,
		}
	}

	function queuedMessageFallback(
		messageId: string,
		message: QueuedSteeringMessage
	): ApiMessage | null {
		const activeThread = chatStore.activeThread
		if (!activeThread) return null
		const content =
			message.content && message.content.length > 0
				? message.content
				: message.text.trim()
					? ([{ type: 'text', text: message.text.trim() }] as ApiMessage['content'])
					: []
		const createdAt = new SvelteDate(message.createdAt).toISOString()
		const metadata: Record<string, unknown> = {
			steering_state: 'queued',
			run_id: message.runId,
			steering_enqueued_at: createdAt,
		}
		if (message.clientSteeringId) metadata.client_steering_id = message.clientSteeringId
		return {
			id: messageId,
			thread_id: activeThread.id,
			parent_id: null,
			type: 'user',
			content,
			tool_calls: [],
			metadata_: metadata,
			sender_agent_id: null,
			sender_user_id: currentUserId,
			created_at: createdAt,
			updated_at: createdAt,
		} satisfies ApiMessage
	}

	function injectQueuedSteeringMessage(
		messageId: string,
		message?: ApiMessage,
		options?: { runId?: string; parentId?: string | null; createdAt?: string | null }
	): boolean {
		const queued = queuedSteeringById.get(messageId)
		const source =
			message ??
			queued?.message ??
			messageTree.get(messageId) ??
			(queued ? queuedMessageFallback(messageId, queued) : null)
		if (!source) return false
		const injected = injectedMessage(messageId, source, options)
		queuedSteeringById.delete(messageId)
		messageTree.set(messageId, injected)
		currentLeafId = messageId
		return true
	}

	function setSteeringParentOverride(runId: string, parentId: string): void {
		steeringParentOverrides.set(runId, parentId)
	}

	function consumeSteeringParentOverride(runId: string | null): string | null {
		if (!runId) return null
		const parentId = steeringParentOverrides.get(runId)
		if (!parentId) return null
		steeringParentOverrides.delete(runId)
		return parentId
	}

	// scroll management
	// position-based auto-scroll: every scroll event checks if we're at the
	// bottom. if yes → autoScroll stays/becomes true. if no → false.
	function handleScroll() {
		if (!scrollContainer) return
		autoScroll = computeIsAtBottom(scrollContainer)

		// avoid runaway paging during initial mount/auto-scroll.
		// initialScrollDone is set once we have loaded and pinned to bottom.
		if (!initialScrollDone) return
		if (scrollContainer.scrollTop <= 80) {
			const threadId = chatStore.activeThread?.id
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
		scrollRequestedWhileQueued = true
		if (scrollQueued) return
		scrollQueued = true
		await tick()
		requestAnimationFrame(() => {
			if (!autoScroll) {
				scrollQueued = false
				scrollRequestedWhileQueued = false
				return
			}
			scrollRequestedWhileQueued = false
			scrollToBottom(behavior)
			requestAnimationFrame(() => {
				if (autoScroll) scrollToBottom('auto')
				scrollQueued = false
				if (scrollRequestedWhileQueued) void queueScrollToBottom('auto')
			})
		})
	}

	// thread lifecycle
	function setThread(t: Thread | null) {
		chatStore.activeThread = t
	}

	function beginThreadLoad(threadId: string): number {
		targetThreadId = threadId
		threadLoadToken += 1
		return threadLoadToken
	}

	function isThreadLoadCurrent(threadId: string, token: number): boolean {
		return targetThreadId === threadId && threadLoadToken === token
	}

	function clearThread() {
		targetThreadId = null
		threadLoadToken += 1
		chatStore.activeThread = null
		messageTree.clear()
		currentLeafId = null
		isThreadLoading = false
		hasLoadedBranch = false
		// reset pagination state so in-flight requests from the previous thread
		// cannot corrupt the next thread's skip counter
		messageSkip = 0
		hasMoreMessages = true
		// abort any active stream so the backend run is cancelled
		runAbortController?.abort()
		runAbortController = null
		// invalidate the run generation: any in-flight stream consumer that
		// hasn't yet observed the abort will see runId !== activeRun on its
		// next iteration and bail before writing more state. without this,
		// a still-running consumeStream from the previous thread will keep
		// poisoning the new thread's messageTree / currentLeafId / streaming
		// assistant for the brief window between abort() and stream exit.
		activeRun += 1
		runCitationAccumulator = []
		citationTargetMessageId = null
		// reset generation state so the resume mechanism can re-fire on the
		// next thread we land on (tryResumeRun bails when isGenerating is
		// already true, and the previous resume's finally may not have run
		// yet by the time we re-mount on the same chat).
		isGenerating = false
		// clear run state to prevent leaking to other chats
		optimisticUserMessage = null
		queuedSteeringById.clear()
		steeringParentOverrides.clear()
		pendingSteeringFlushInFlight = false
		streamingAssistant = null
		streamingAssistantParentId = null
		viewingStreamingBranch = true
		streamingLeafId = null
		lastRunInput = ''
		runBlocks = []
		// clear message event tracking for previous thread
		fetchedEventMessageIds.clear()
		eventMessageIdsPending.clear()
		toolTracker.clear()
		runActivities.clear()
		citationSources.clear()
	}

	// unified state object
	// single object serving both as ChatContext for module functions and
	// ChatState for the page UI. eliminates the double-proxy pattern.
	const state: ChatState = {
		// thread
		get thread() {
			return chatStore.activeThread
		},
		set thread(v) {
			chatStore.activeThread = v
		},

		// message tree
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

		// streaming
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
		get queuedSteeringMessages() {
			return queuedSteeringMessages
		},
		stageQueuedSteeringMessage,
		removeQueuedSteeringMessage,
		confirmQueuedSteeringMessage,
		flushPendingSteeringMessages,
		injectQueuedSteeringMessage,
		setSteeringParentOverride,
		consumeSteeringParentOverride,
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

		// paging
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

		// scroll
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

		// tools
		get toolTracker() {
			return toolTracker
		},
		get fetchedEventMessageIds() {
			return fetchedEventMessageIds
		},
		get eventMessageIdsPending() {
			return eventMessageIdsPending
		},
		get eventsInFlight() {
			return eventsInFlight
		},
		set eventsInFlight(v) {
			eventsInFlight = v
		},
		get runActivities() {
			return runActivities
		},
		processRunActivityEvent,

		get citationSources() {
			return citationSources
		},
		get citationTargetMessageId() {
			return citationTargetMessageId
		},
		set citationTargetMessageId(v: string | null) {
			citationTargetMessageId = v
		},
		addCitationSources(citations: ApiCitation[]) {
			runCitationAccumulator.push(...citations)
			// live-update the reactive map so both MarkdownRenderer and the
			// sources pill see new citations immediately. prefer the active
			// streaming message; fall back to the last finalized message for
			// late WS events that arrive after the SSE stream finished.
			const targetId = streamingAssistant?.messageId ?? citationTargetMessageId
			if (targetId) {
				citationSources.set(targetId, [...runCitationAccumulator])
			}
		},
		flushCitationsToMessage(messageId: string) {
			if (runCitationAccumulator.length > 0) {
				citationSources.set(messageId, [...runCitationAccumulator])
			}
		},

		// realtime
		get typingUsers() {
			return typingUsers
		},

		// derived
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

		// page-specific state
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

		// coordinator methods
		get threadLoadToken() {
			return threadLoadToken
		},
		beginThreadLoad,
		isThreadLoadCurrent,
		incrementActiveRun() {
			runCitationAccumulator = []
			citationTargetMessageId = null
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

		// delegated to $lib/chat modules
		loadTree: (threadId) => loadTree(threadId, state),
		handleSendMessage: (content, modifiers) => handleSendMessage(content, state, modifiers),
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
		dropSteering: async (runId, messageId) => {
			if (!state.thread) return
			const queued = queuedSteeringById.get(messageId)
			if (queued?.deliveryState === 'sending') {
				state.removeQueuedSteeringMessage(messageId)
				return
			}
			try {
				await dropSteeringApi(runId, messageId)
				state.removeQueuedSteeringMessage(messageId)
			} catch (e) {
				console.error('failed to drop steering message', e)
			}
		},
		switchBranch: (messageId, direction) => switchBranch(messageId, direction, state),
		findRunUserMessage: (block) => findRunUserMessage(block, state),
		subscribeToChatEvents: (threadId) => subscribeToChatEvents(threadId, state),
		sendTypingEvent,
	}

	return state
}

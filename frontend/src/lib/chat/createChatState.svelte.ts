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

	// streaming text coalescing: SSE token deltas buffer here and flush to
	// streamingAssistant.content once per frame, so per-token markdown re-render
	// and the scroll effect collapse to at most once per frame. flushed
	// synchronously at every boundary that reads streamingAssistant.content.
	let pendingStreamText = ''
	let pendingStreamMessageId: string | null = null
	let streamTextRaf: number | null = null

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
	// intent-based pin: `autoScroll` flips ONLY on genuine user gestures (see
	// onUserScrollGesture + handleScroll), never from our own scrolls or content
	// reflow.  these timestamps mark windows during which a scroll event is
	// attributed to a program/reflow (suppress pin change) or to the user (force
	// pin re-evaluation even inside a programmatic window).
	let programmaticScrollUntil = 0
	let userScrollUntil = 0
	// monotonic request counter for the scroll coalescer: the chain re-runs only
	// when a genuinely new request arrived (no sticky boolean -> no busy loop).
	let scrollReqSeq = 0
	let scrollChainRunning = false

	// entrance animation: ids of messages that arrived live from another session
	// (cross-device sync) and should play the fallback entrance once, on mount.
	// marked by the WS handler for live tail-appends only — never on load,
	// branch-switch, or pagination — so history doesn't animate.
	const messageEntranceIds = new SvelteSet<string>()

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

	function flushStreamingText(): void {
		if (streamTextRaf !== null) {
			cancelAnimationFrame(streamTextRaf)
			streamTextRaf = null
		}
		if (!pendingStreamText) return
		// only apply if the buffer still belongs to the live streaming message;
		// a supersede/abort can swap the message out from under us.
		if (streamingAssistant && streamingAssistant.messageId === pendingStreamMessageId) {
			streamingAssistant.content += pendingStreamText
		}
		pendingStreamText = ''
		pendingStreamMessageId = null
	}

	function appendStreamingText(text: string): void {
		if (!streamingAssistant || !text) return
		if (
			pendingStreamMessageId !== null &&
			pendingStreamMessageId !== streamingAssistant.messageId
		) {
			pendingStreamText = ''
		}
		pendingStreamMessageId = streamingAssistant.messageId
		pendingStreamText += text
		if (streamTextRaf !== null) return
		if (typeof requestAnimationFrame !== 'function') {
			flushStreamingText()
			return
		}
		streamTextRaf = requestAnimationFrame(flushStreamingText)
	}

	// run block management
	function rebuildRunBlocks(): void {
		// every structural rebuild reads streamingAssistant.content; apply any
		// buffered tokens first so block structure and content stay consistent.
		flushStreamingText()
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

	// scroll management — intent-based pin.
	// the pin (`autoScroll`) reflects whether the USER wants the view to follow
	// new content.  it flips only on genuine user gestures: a scroll event counts
	// as user-driven when it lands in a user-gesture window OR outside the
	// programmatic-scroll window.  this keeps the view pinned through fast
	// streaming and run-end reflow (whose scroll events are suppressed) while
	// detaching the instant the user scrolls up.
	const PROGRAMMATIC_AUTO_MS = 150
	const PROGRAMMATIC_SMOOTH_MS = 700
	const USER_GESTURE_MS = 500

	function nextAnimationFrame(): Promise<void> {
		return new Promise((resolve) => requestAnimationFrame(() => resolve()))
	}

	// mark an imminent programmatic scroll so the scroll event(s) it triggers do
	// not flip the pin.  exposed so non-scrollTo programmatic writes (e.g. the
	// pagination scroll-anchor restore in dataLoader) can suppress intent too.
	function markProgrammaticScroll(behavior: 'auto' | 'smooth' = 'auto') {
		programmaticScrollUntil =
			performance.now() +
			(behavior === 'smooth' ? PROGRAMMATIC_SMOOTH_MS : PROGRAMMATIC_AUTO_MS)
	}

	// called by the page on a genuine user scroll gesture (wheel / touch).  an
	// upward gesture detaches immediately (bypassing the programmatic window,
	// which is otherwise perpetually open during streaming); other directions
	// open a window so the resulting scroll events re-evaluate the pin from
	// position — re-pinning when the user returns to the bottom, even mid-stream.
	function onUserScrollGesture(direction: 'up' | 'down' | 'unknown' = 'unknown') {
		userScrollUntil = performance.now() + USER_GESTURE_MS
		if (direction === 'up') autoScroll = false
	}

	function handleScroll() {
		if (!scrollContainer) return
		const now = performance.now()
		// update the pin from position only for genuine user scrolls — never for
		// our own scrollTo or content reflow (those fall inside the programmatic
		// window and would otherwise detach the user during streaming/run-end).
		if (now <= userScrollUntil || now > programmaticScrollUntil) {
			autoScroll = computeIsAtBottom(scrollContainer)
		}

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
		markProgrammaticScroll(behavior)
		scrollContainer.scrollTo({ top: scrollContainer.scrollHeight, behavior })
	}

	// coalesced scroll-to-bottom.  single-flight via a monotonic request counter:
	// while a chain runs, new calls just bump the counter and the chain runs one
	// more pass for them; it stops as soon as no new request arrived or the pin
	// was released.  never drops a request, never busy-loops.
	async function queueScrollToBottom(behavior: 'auto' | 'smooth' = 'auto') {
		if (!scrollContainer) return
		scrollReqSeq += 1
		if (scrollChainRunning) return
		scrollChainRunning = true
		try {
			let handled = -1
			while (handled !== scrollReqSeq) {
				handled = scrollReqSeq
				await tick()
				if (!autoScroll) return
				await nextAnimationFrame()
				if (!autoScroll) return
				scrollToBottom(behavior)
				// instant correction pass after layout settles (covers late
				// reflow).  skipped for smooth so the animation isn't cut short.
				await nextAnimationFrame()
				if (autoScroll && behavior === 'auto') scrollToBottom('auto')
			}
		} finally {
			scrollChainRunning = false
		}
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
		messageEntranceIds.clear()
		steeringParentOverrides.clear()
		pendingSteeringFlushInFlight = false
		if (streamTextRaf !== null) {
			cancelAnimationFrame(streamTextRaf)
			streamTextRaf = null
		}
		pendingStreamText = ''
		pendingStreamMessageId = null
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
		markMessageEntrance(id: string) {
			messageEntranceIds.add(id)
		},
		consumeMessageEntrance(id: string) {
			if (!messageEntranceIds.has(id)) return false
			messageEntranceIds.delete(id)
			return true
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
		appendStreamingText,
		flushStreamingText,
		queueScrollToBottom,
		handleScroll,
		scrollToBottom,
		onUserScrollGesture,
		markProgrammaticScroll,
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

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
import { loadNewerMessages, loadOlderMessages, loadTree } from './dataLoader'
import { sendTypingEvent, subscribeToChatEvents } from './eventSubscriptions.svelte'
import {
	AUTO_SCROLL_BUFFER_PX,
	buildAgentLookup,
	buildMessageChildren,
	buildRunBlocks,
	computeIsAtBottom,
	type RunBlock,
	type StreamingAssistantState,
} from './helpers'
import { buildParticipantIndex, buildThreadAgentIndex } from './participants'
import { reduceRunActivityEvent, runActivityKey } from './runActivities'
import {
	dropSteering as dropSteeringApi,
	SteeringRunNotFoundError,
	steerRun as steerRunApi,
} from './steering'
import { resumeCreateAndRun } from './streamProcessor'
import type { ChatSystemEvent } from './systemEvents'
import { findRunUserMessage, switchBranch } from './treeNavigation'
import type {
	ApiCitation,
	ApiMessage,
	ChatState,
	OptimisticUserMessage,
	QueuedSteeringMessage,
	RunActivityEvent,
	RunActivityState,
	RunFailureEntry,
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

	// a run that has stopped emitting text is still running, and a bubble frozen
	// mid-sentence reads as broken. after this long without a token the text
	// placeholder comes back at the end of what is written so far. long enough
	// that ordinary between-token pauses never trip it, short enough that a real
	// stall is admitted while the reader is still looking at it.
	const STREAM_TEXT_STALL_MS = 2000
	let streamTextStalled = $state(false)
	let streamStallTimer: ReturnType<typeof setTimeout> | null = null

	// thread state (activeThread in chatStore is the source of truth)
	let isThreadLoading = $state(false)
	let hasLoadedBranch = $state(false)
	let targetThreadId = $state<string | null>(null)
	let threadLoadToken = 0

	// message paging (latest-first from backend)
	let messageSkip = $state(0)
	let hasMoreMessages = $state(true)
	let isLoadingOlderMessages = $state(false)
	let hasNewerMessages = $state(false)
	let isLoadingNewerMessages = $state(false)
	let branchCursorTowardRoot = $state<string | null>(null)
	let branchCursorTowardLeaf = $state<string | null>(null)
	let initialAnchorMessageId = $state<string | null>(null)
	const siblingCounts = new SvelteMap<string, number>()

	// message tree (for branching)
	const messageTree = new SvelteMap<string, ApiMessage>()
	let currentLeafId = $state<string | null>(null)

	// scroll state
	let scrollContainer = $state<HTMLElement | null>(null)
	let inputOverlay = $state<HTMLElement | null>(null)
	let autoScroll = $state(true)
	// whether the transcript is actually taller than its viewport. a wheel tick
	// releases the pin even when there is nothing to scroll, so "not pinned" on
	// its own is not evidence that a scroll-to-bottom affordance is useful.
	let canScroll = $state(false)
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
	// scroll offset the last paging decision saw, so a trigger fires only when
	// the view actually MOVED toward that edge - a page that lands on an edge
	// and stays there never re-arms itself.
	let lastPagingScrollTop = 0
	// single-flight guard for the viewport backfill below
	let backfillRunning = false
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
	// keyed by event id: the same failure arrives live and again on reload
	const runFailures = new SvelteMap<string, RunFailureEntry>()
	// inline system rows (membership, renames), keyed the same way
	const systemEvents = new SvelteMap<string, ChatSystemEvent>()

	// citation sources - message-scoped map populated from citation.sources WS events.
	// keyed by assistant message_id so each message has its own citation set.
	const citationSources = new SvelteMap<string, ApiCitation[]>()
	// run-level accumulator: citations are cumulative across iterations within
	// a single run. flushed into citationSources per-message on stream start.
	let runCitationAccumulator: ApiCitation[] = []
	// last finalized assistant message id - fallback target for late WS citation
	// events that arrive after the SSE stream has already finalized the message.
	let citationTargetMessageId: string | null = null

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

	/** agents in THIS thread; authoritative over the viewer-scoped agent store. */
	const threadAgentById = $derived(buildThreadAgentIndex(chatStore.activeThread))
	const agentNameById = $derived.by(() => {
		const names = buildAgentLookup(agents.list, (a) => a.name)
		for (const [id, agent] of threadAgentById) names.set(id, agent.name)
		return names
	})
	const agentAvatarById = $derived.by(() => {
		const avatars = buildAgentLookup(agents.list, (a) => a.profile_image_url ?? null)
		for (const [id, agent] of threadAgentById) avatars.set(id, agent.avatarUrl)
		return avatars
	})
	/** human identities for this thread, resolved from its participant roster. */
	const participantById = $derived(buildParticipantIndex(chatStore.activeThread))

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

	/** stop watching for a stall and clear it (stream ended, or swapped bubble). */
	function resetStreamTextStall(): void {
		if (streamStallTimer !== null) {
			clearTimeout(streamStallTimer)
			streamStallTimer = null
		}
		streamTextStalled = false
	}

	/** a token landed: clear any stall and re-arm the watch for the next one. */
	function noteStreamingTextChunk(): void {
		resetStreamTextStall()
		streamStallTimer = setTimeout(() => {
			streamStallTimer = null
			streamTextStalled = true
		}, STREAM_TEXT_STALL_MS)
	}

	function appendStreamingText(text: string): void {
		if (!streamingAssistant || !text) return
		noteStreamingTextChunk()
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
			runFailures: Array.from(runFailures.values()),
			systemEvents: Array.from(systemEvents.values()),
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

	/**
	 * whether THIS client queued the message as text steering.
	 *
	 * invocation is server-owned, so `run.steering.*` also fires for ordinary
	 * messages a user simply wrote. only a message the client queued itself is
	 * a ghost bubble; everything else is run progress and must render normally.
	 */
	function ownsSteeringMessage(messageId: string): boolean {
		if (queuedSteeringById.has(messageId)) return true
		for (const serverId of queuedSteeringServerIdsByClientId.values()) {
			if (serverId === messageId) return true
		}
		return false
	}

	/** merge a message-anchored run activity event and refresh visible run blocks. */
	function processRunActivityEvent(event: RunActivityEvent): void {
		const key = runActivityKey(event)
		runActivities.set(key, reduceRunActivityEvent(runActivities.get(key), event))
		rebuildRunBlocks()
	}

	/** record a durable run failure. immutable, so a known id is left alone. */
	function recordRunFailure(failure: RunFailureEntry): void {
		if (runFailures.has(failure.id)) return
		runFailures.set(failure.id, failure)
		// the transient error bubble and this record describe the SAME failure.
		// the durable one survives reload and reaches every participant, so it
		// wins; keeping both renders the failure twice.
		if (streamingAssistant?.isError && streamingAssistant.runId === failure.runId) {
			streamingAssistant = null
		}
		rebuildRunBlocks()
	}

	/** record an inline system row. immutable, so a known id is left alone. */
	function recordSystemEvent(event: ChatSystemEvent): void {
		if (systemEvents.has(event.id)) return
		systemEvents.set(event.id, event)
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
		const meta = (message.metadata ?? {}) as Record<string, unknown>
		const runId = options?.runId ?? (typeof meta.run_id === 'string' ? meta.run_id : null)
		const metadata: Record<string, unknown> = { ...meta, steering_state: 'injected' }
		if (runId) metadata.run_id = runId
		if (options?.createdAt) metadata.steering_injected_at = options.createdAt
		return {
			...message,
			parent_id: options?.parentId ?? message.parent_id,
			created_at: options?.createdAt ?? message.created_at,
			updated_at: options?.createdAt ?? message.updated_at,
			metadata: metadata,
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
			metadata: metadata,
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
		// an injected steering message graduates a ghost bubble into the thread.
		// a message already sitting in the tree that this client never queued is
		// an ordinary one a server-owned catch-up handed to the run, so marking
		// it injected would restyle real conversation as steering.
		if (!queued && !message && messageTree.has(messageId)) return false
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

	// how close to each end of the loaded window a reader has to get before the
	// next page is fetched.
	const PAGE_UP_TRIGGER_PX = 80
	const PAGE_DOWN_TRIGGER_PX = 160
	// pages one viewport backfill may pull before it gives up
	const BACKFILL_MAX_PAGES = 3

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
		// a thread opens parked ON an edge, and a gesture against an edge moves
		// nothing - so it fires no scroll event at all. the pull is then the only
		// signal paging ever gets that the reader wants what is past it.
		const toward = direction === 'unknown' ? restingEdge() : direction
		if (toward) pageTowardEdge(toward)
	}

	/** the end the view sits against, when it sits against exactly one. */
	function restingEdge(): 'up' | 'down' | null {
		if (!scrollContainer) return null
		const atTop = scrollContainer.scrollTop <= PAGE_UP_TRIGGER_PX
		const atBottom = distanceToBottom() <= PAGE_DOWN_TRIGGER_PX
		if (atTop === atBottom) return null
		return atTop ? 'up' : 'down'
	}

	function distanceToBottom(): number {
		if (!scrollContainer) return 0
		return (
			scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight
		)
	}

	/**
	 * fetch the next page toward one end, if the view is sitting at that end.
	 *
	 * one page at a time and one direction at a time: a load in flight owns the
	 * window, so the far edge cannot start a second one under it.
	 */
	function pageTowardEdge(direction: 'up' | 'down'): void {
		if (!scrollContainer) return
		if (!initialScrollDone) return
		const threadId = chatStore.activeThread?.id
		if (!threadId) return
		if (isLoadingOlderMessages || isLoadingNewerMessages) return
		if (direction === 'up') {
			if (!hasMoreMessages) return
			if (scrollContainer.scrollTop > PAGE_UP_TRIGGER_PX) return
			void loadOlderMessages(threadId, state)
			return
		}
		if (!hasNewerMessages) return
		if (distanceToBottom() > PAGE_DOWN_TRIGGER_PX) return
		void loadNewerMessages(threadId, state)
	}

	/** re-measure whether the transcript overflows its viewport. */
	function measureScrollable(): void {
		if (!scrollContainer) {
			canScroll = false
			return
		}
		canScroll =
			scrollContainer.scrollHeight - scrollContainer.clientHeight > AUTO_SCROLL_BUFFER_PX
	}

	// the bottom of the loaded window is not the bottom of the conversation
	// while pages toward the leaf are still missing, so the pin stays off until
	// the tail is there - otherwise every downward page drags the reader along.
	function canPinToBottom(): boolean {
		return !hasNewerMessages
	}

	// content resized without a gesture (a hover toolbar sliding out, a bubble
	// collapsing): if that left the view at the bottom, the pin is back on.
	// never detaches - only gestures express intent to leave.
	function onContentResize(): void {
		measureScrollable()
		if (
			!autoScroll &&
			canPinToBottom() &&
			scrollContainer &&
			computeIsAtBottom(scrollContainer)
		)
			autoScroll = true
		void backfillViewport()
	}

	/**
	 * fill the viewport when the loaded window does not.
	 *
	 * a page can be shorter than the screen (short messages, a tall display), and
	 * then no scroll event ever fires: the transcript would sit in a half-empty
	 * window with no way to ask for more. this is the deliberate way out - one
	 * page at a time, one direction at a time, re-measuring in between, so it can
	 * never race the scroll triggers or ping-pong against itself.
	 */
	async function backfillViewport(): Promise<void> {
		if (backfillRunning) return
		if (!hasLoadedBranch || !scrollContainer) return
		if (isLoadingOlderMessages || isLoadingNewerMessages) return
		const threadId = chatStore.activeThread?.id
		if (!threadId) return
		measureScrollable()
		if (canScroll) return

		backfillRunning = true
		try {
			for (let page = 0; page < BACKFILL_MAX_PAGES; page += 1) {
				const container = scrollContainer
				if (!container || threadId !== chatStore.activeThread?.id) return
				const heightBefore = container.scrollHeight
				// toward the leaf first: it appends below the reader instead of
				// prepending above them, so nothing they are looking at moves.
				if (hasNewerMessages) await loadNewerMessages(threadId, state)
				else if (hasMoreMessages) await loadOlderMessages(threadId, state)
				else return
				await tick()
				if (!scrollContainer || threadId !== chatStore.activeThread?.id) return
				measureScrollable()
				// filled, or the page added nothing: either way, stop asking.
				if (canScroll || scrollContainer.scrollHeight <= heightBefore) return
			}
		} finally {
			backfillRunning = false
		}
	}

	function handleScroll() {
		if (!scrollContainer) return
		measureScrollable()
		const now = performance.now()
		// update the pin from position only for genuine user scrolls — never for
		// our own scrollTo or content reflow (those fall inside the programmatic
		// window and would otherwise detach the user during streaming/run-end).
		if (now <= userScrollUntil || now > programmaticScrollUntil) {
			autoScroll = canPinToBottom() && computeIsAtBottom(scrollContainer)
		}

		const scrollTop = scrollContainer.scrollTop
		const movedBy = scrollTop - lastPagingScrollTop
		lastPagingScrollTop = scrollTop

		// avoid runaway paging during initial mount/auto-scroll.
		// initialScrollDone is set once we have loaded and pinned to bottom.
		if (!initialScrollDone) return
		// paging follows the reader, never the layout settling into place. a
		// thread that opens mid-history parks the view with a programmatic scroll
		// that lands ON an edge, and a page restore jumps it again - read as
		// arrivals, those fire both directions before anyone has scrolled. the
		// test is stricter than the pin's: a gesture window does NOT excuse a
		// scroll we drove, or the restore right after a scroll-up would page down.
		if (now <= programmaticScrollUntil) return

		if (movedBy < 0) pageTowardEdge('up')
		else if (movedBy > 0) pageTowardEdge('down')
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
		hasNewerMessages = false
		isLoadingNewerMessages = false
		branchCursorTowardRoot = null
		branchCursorTowardLeaf = null
		initialAnchorMessageId = null
		lastPagingScrollTop = 0
		siblingCounts.clear()
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
		resetStreamTextStall()
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
		runFailures.clear()
		systemEvents.clear()
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
			// a different bubble (or none) means the stall watch belongs to a
			// stream that is over.
			if (v === null || v.messageId !== streamingAssistant?.messageId) resetStreamTextStall()
			streamingAssistant = v
		},
		get isStreamingTextStalled() {
			return streamTextStalled
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
		ownsSteeringMessage,
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
		get hasNewerMessages() {
			return hasNewerMessages
		},
		set hasNewerMessages(v) {
			hasNewerMessages = v
		},
		get isLoadingNewerMessages() {
			return isLoadingNewerMessages
		},
		set isLoadingNewerMessages(v) {
			isLoadingNewerMessages = v
		},
		get branchCursorTowardRoot() {
			return branchCursorTowardRoot
		},
		set branchCursorTowardRoot(v) {
			branchCursorTowardRoot = v
		},
		get branchCursorTowardLeaf() {
			return branchCursorTowardLeaf
		},
		set branchCursorTowardLeaf(v) {
			branchCursorTowardLeaf = v
		},
		get initialAnchorMessageId() {
			return initialAnchorMessageId
		},
		set initialAnchorMessageId(v) {
			initialAnchorMessageId = v
		},
		siblingCounts,

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
		get canScroll() {
			return canScroll
		},
		measureScrollable,
		onContentResize,

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
		get runFailures() {
			return runFailures
		},
		recordRunFailure,
		get systemEvents() {
			return systemEvents
		},
		recordSystemEvent,

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
		get participantById() {
			return participantById
		},
		get agentNameById() {
			return agentNameById
		},
		get agentAvatarById() {
			return agentAvatarById
		},
		get threadAgentById() {
			return threadAgentById
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
		loadTree: (threadId, options) => loadTree(threadId, state, options),
		handleSendMessage: (content, modifiers) => handleSendMessage(content, state, modifiers),
		handleRegenerateMessage: (parentId, prompt, agentId) =>
			handleRegenerateMessage(parentId ?? null, state, prompt, agentId),
		handleStopGeneration: () => handleStopGeneration(state),
		handleSaveEditMessage: (messageId, newContent) =>
			handleSaveEditMessage(messageId, newContent, state),
		handleSaveAsCopyMessage: (messageId, newContent) =>
			handleSaveAsCopyMessage(messageId, newContent, state),
		resumeCreateAndRun: (stream, threadId) => resumeCreateAndRun(stream, threadId, state),
		requestDeleteUserMessage: (messageId) => requestDeleteUserMessage(messageId, state),
		deleteUserMessage: (messageId, options) => deleteUserMessage(messageId, state, options),
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

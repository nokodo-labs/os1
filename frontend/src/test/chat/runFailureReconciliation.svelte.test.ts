/**
 * a failed run is reconciled from the backend's own events, never invented.
 *
 * the client may bridge the gap with a temporary bubble so the screen does not
 * flash, but the persisted `message.created` (which the backend emits before
 * `run.error`) replaces it in place, and the durable failure renders from
 * run-failure state. nothing temporary may survive in the message tree.
 */

import { isOwnEvent } from '$lib/api/sessionId'
import { subscribeToChatEvents } from '$lib/chat/eventSubscriptions.svelte'
import { isPlaceholderMessageId } from '$lib/chat/helpers'
import { parseRunFailureEvent } from '$lib/chat/runFailures'
import type {
	ApiMessage,
	ChatContext,
	QueuedSteeringMessage,
	RunFailureEntry,
} from '$lib/chat/types'
import { handleRegenerateMessage, handleSendMessage } from '$lib/chat/userActions'
import { ToolExecutionTracker } from '$lib/tools'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeStreamMessage, makeThread, resetIdCounter } from './fixtures'

let capturedHandler: ((msg: unknown) => void) | null = null

vi.mock('$lib/api/sessionId', () => ({
	isOwnEvent: vi.fn(() => true),
}))

vi.mock('$lib/api/streaming/eventStream.svelte', () => ({
	eventStreamClient: {
		subscribe: vi.fn((handler: (msg: unknown) => void) => {
			capturedHandler = handler
			return () => {
				capturedHandler = null
			}
		}),
		send: vi.fn(),
	},
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		runs: new Map(),
		getRunsForThread: vi.fn(() => []),
		forgetRun: vi.fn(),
	},
}))

vi.mock('$lib/stores/selectedAgent.svelte', () => ({
	selectedAgent: { id: 'agent_1' },
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: { get: vi.fn(() => undefined) },
}))

vi.mock('$lib/chat/dataLoader', () => ({
	loadTree: vi.fn(),
	syncCacheAfterRun: vi.fn(),
}))

const streamMocks = vi.hoisted(() => ({ runThreadStream: vi.fn() }))

vi.mock('$lib/chat/streamProcessor', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/chat/streamProcessor')>()),
	runThreadStream: streamMocks.runThreadStream,
}))

const ANCHOR_ID = 'u1'
const PARTIAL_ID = 'a1'
const RUN_ID = 'run_1'

function makeContext(): ChatContext {
	const messageTree = new SvelteMap<string, ApiMessage>()
	const runFailures = new SvelteMap<string, RunFailureEntry>()
	const queuedSteeringMessages: QueuedSteeringMessage[] = []
	const ctx: ChatContext = {
		thread: makeThread({ id: 'thread_1' }),
		messageTree,
		messageChildren: new Map(),
		currentLeafId: ANCHOR_ID,
		messages: [],
		isGenerating: false,
		activeRun: 1,
		streamingAssistant: null,
		streamingAssistantParentId: null,
		streamingLeafId: null,
		viewingStreamingBranch: true,
		optimisticUserMessage: null,
		queuedSteeringMessages,
		lastRunInput: '',
		inputValue: '',
		runAbortController: null,
		stageQueuedSteeringMessage(message) {
			queuedSteeringMessages.push(message)
		},
		removeQueuedSteeringMessage() {},
		ownsSteeringMessage() {
			return false
		},
		confirmQueuedSteeringMessage() {
			return false
		},
		async flushPendingSteeringMessages() {},
		injectQueuedSteeringMessage() {
			return false
		},
		setSteeringParentOverride() {},
		consumeSteeringParentOverride() {
			return null
		},
		markMessageEntrance() {},
		consumeMessageEntrance() {
			return false
		},
		messageSkip: 0,
		hasMoreMessages: false,
		hasNewerMessages: false,
		isLoadingNewerMessages: false,
		branchCursorTowardRoot: null,
		branchCursorTowardLeaf: null,
		initialAnchorMessageId: null,
		siblingCounts: new SvelteMap<string, number>(),
		isLoadingOlderMessages: false,
		scrollContainer: null,
		autoScroll: true,
		measureScrollable() {},
		toolTracker: new ToolExecutionTracker(),
		fetchedEventMessageIds: new SvelteSet<string>(),
		eventMessageIdsPending: new SvelteSet<string>(),
		eventsInFlight: false,
		runActivities: new SvelteMap(),
		processRunActivityEvent() {},
		runFailures,
		// mirrors createChatState: the durable record replaces the transient
		// bubble that described the same failure
		recordRunFailure(failure) {
			if (runFailures.has(failure.id)) return
			runFailures.set(failure.id, failure)
			if (ctx.streamingAssistant?.isError && ctx.streamingAssistant.runId === failure.runId) {
				ctx.streamingAssistant = null
			}
		},
		systemEvents: new SvelteMap(),
		recordSystemEvent() {},
		citationSources: new SvelteMap(),
		citationTargetMessageId: null,
		addCitationSources() {},
		flushCitationsToMessage() {},
		isTemporaryChat: false,
		currentUserId: 'user_1',
		threadLoadToken: 0,
		beginThreadLoad() {
			return 0
		},
		isThreadLoadCurrent() {
			return true
		},
		incrementActiveRun() {
			ctx.activeRun += 1
			return ctx.activeRun
		},
		rebuildRunBlocks() {},
		appendStreamingText() {},
		flushStreamingText() {},
		async queueScrollToBottom() {},
		markProgrammaticScroll() {},
	}
	messageTree.set(
		ANCHOR_ID,
		makeApiMessage({ id: ANCHOR_ID, thread_id: 'thread_1', sender_user_id: 'user_1' })
	)
	return ctx
}

function dispatch(msg: unknown): void {
	if (!capturedHandler) throw new Error('no handler registered')
	capturedHandler(msg)
}

/** the persisted partial, exactly as the backend broadcasts it. */
function partialMessageEvent() {
	return makeStreamMessage(
		'message.created',
		{
			...makeApiMessage({
				id: PARTIAL_ID,
				thread_id: 'thread_1',
				parent_id: ANCHOR_ID,
				type: 'assistant',
				sender_user_id: null,
				sender_agent_id: 'agent_1',
				content: [{ type: 'text', text: 'half an answer' }],
				metadata: { run_id: RUN_ID, partial: true, partial_reason: 'error' },
			}),
		},
		{ id: 'event_partial', thread_id: 'thread_1' }
	)
}

function runErrorEvent() {
	return makeStreamMessage(
		'run.error',
		{
			thread_id: 'thread_1',
			agent_id: 'agent_1',
			run_id: RUN_ID,
			reason: 'provider_error',
			partial_message_id: PARTIAL_ID,
		},
		{
			id: 'event_failure',
			thread_id: 'thread_1',
			message_id: ANCHOR_ID,
			created_at: new Date().toISOString(),
		}
	)
}

/**
 * the transport drops mid-run: tokens rendered into the bridge, but no frame
 * ever named the message the backend reserved for them.
 */
function dropAfterStreaming(ctx: ChatContext): void {
	streamMocks.runThreadStream.mockImplementation(async () => {
		const bridge = ctx.streamingAssistant
		if (bridge) {
			bridge.runId = RUN_ID
			bridge.content = 'half an answer'
		}
		throw new Error('lost connection to the run')
	})
}

describe('a run that failed after streaming', () => {
	beforeEach(() => {
		resetIdCounter()
		streamMocks.runThreadStream.mockReset()
		vi.mocked(isOwnEvent).mockReturnValue(true)
	})

	afterEach(() => {
		capturedHandler = null
	})

	it('keeps the streamed text on the bridge instead of writing a local partial', async () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		dropAfterStreaming(ctx)

		await handleSendMessage('hello', ctx)

		// the text stays on screen until the real message lands - and the tree
		// holds nothing the backend cannot resolve
		expect(ctx.streamingAssistant?.content).toBe('half an answer')
		expect(ctx.streamingAssistant?.isError).toBe(true)
		expect([...ctx.messageTree.keys()]).toEqual([ANCHOR_ID])
		unsubscribe()
	})

	it('replaces the bridge in place when the persisted partial arrives', async () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		dropAfterStreaming(ctx)

		await handleSendMessage('hello', ctx)
		const bridgeId = ctx.streamingAssistant?.messageId ?? ''
		expect(isPlaceholderMessageId(bridgeId)).toBe(true)

		dispatch(partialMessageEvent())

		expect(ctx.messageTree.get(PARTIAL_ID)?.parent_id).toBe(ANCHOR_ID)
		expect(ctx.currentLeafId).toBe(PARTIAL_ID)
		expect(ctx.streamingLeafId).toBe(PARTIAL_ID)
		expect(ctx.streamingAssistantParentId).toBe(PARTIAL_ID)
		expect(ctx.streamingAssistant).toBeNull()
		expect([...ctx.messageTree.keys()].filter(isPlaceholderMessageId)).toEqual([])
		unsubscribe()
	})

	it('renders the failure from the durable record and retries on the real anchor', async () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		dropAfterStreaming(ctx)

		await handleSendMessage('hello', ctx)
		dispatch(partialMessageEvent())
		dispatch(runErrorEvent())

		expect([...ctx.runFailures.values()]).toHaveLength(1)
		const failure = parseRunFailureEvent({
			id: 'event_failure',
			type: 'run.error',
			message_id: ANCHOR_ID,
			data: { thread_id: 'thread_1', agent_id: 'agent_1', run_id: RUN_ID },
		})

		streamMocks.runThreadStream.mockResolvedValue(undefined)
		await handleRegenerateMessage(failure?.anchorMessageId ?? null, ctx, null, 'agent_1')

		const call = streamMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.splice).toEqual({ parent_id: ANCHOR_ID })
		// the failure's own partial is a real message on the branch, so the new
		// attempt forks beside something the backend can resolve
		expect(ctx.messageTree.has(PARTIAL_ID)).toBe(true)
		expect(isPlaceholderMessageId(ctx.streamingAssistantParentId)).toBe(false)
		unsubscribe()
	})

	it('anchors a regeneration on the reconciled message id', async () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		dropAfterStreaming(ctx)

		await handleSendMessage('hello', ctx)
		dispatch(partialMessageEvent())
		dispatch(runErrorEvent())

		streamMocks.runThreadStream.mockResolvedValue(undefined)
		await handleRegenerateMessage(PARTIAL_ID, ctx, null, 'agent_1')

		const call = streamMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.splice).toEqual({ parent_id: PARTIAL_ID })
		unsubscribe()
	})
})

describe('a run that never reached the backend', () => {
	beforeEach(() => {
		resetIdCounter()
		streamMocks.runThreadStream.mockReset()
		vi.mocked(isOwnEvent).mockReturnValue(true)
	})

	it('leaves the tree untouched and marks the message not delivered', async () => {
		const ctx = makeContext()
		streamMocks.runThreadStream.mockRejectedValue(new TypeError('failed to fetch'))

		await handleSendMessage('hello', ctx)

		// nothing was persisted and no event will ever arrive, so there is
		// nothing to reconcile against - and nothing to keep on screen either
		expect([...ctx.messageTree.keys()]).toEqual([ANCHOR_ID])
		expect(ctx.streamingAssistant).toBeNull()
		expect(ctx.streamingLeafId).toBeNull()
		expect(ctx.optimisticUserMessage?.deliveryFailed).toBe(true)
		expect(ctx.currentLeafId).toBe(ANCHOR_ID)
	})
})

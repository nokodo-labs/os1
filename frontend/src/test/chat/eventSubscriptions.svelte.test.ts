import { isOwnEvent } from '$lib/api/sessionId'
import type { ApiMessage, ChatContext, QueuedSteeringMessage } from '$lib/chat/types'
import { ToolExecutionTracker } from '$lib/tools'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeStreamMessage, makeThread } from './fixtures'

let capturedHandler: ((msg: unknown) => void) | null = null

vi.mock('$lib/api/sessionId', () => ({
	isOwnEvent: vi.fn(() => false),
}))

vi.mock('$lib/api/streaming/chatStream', () => ({
	StreamHttpError: class StreamHttpError extends Error {},
	resumeRunStream: vi.fn(),
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
	},
}))

import { subscribeToChatEvents } from '$lib/chat/eventSubscriptions.svelte'

function makeContext(): ChatContext {
	const messageTree = new SvelteMap<string, ApiMessage>()
	const queuedSteeringMessages: QueuedSteeringMessage[] = []
	const steeringParentOverrides = new Map<string, string>()
	const messageEntranceIds = new Set<string>()
	const ctx: ChatContext = {
		thread: makeThread({ id: 'thread_1' }),
		messageTree,
		messageChildren: new Map(),
		currentLeafId: 'assistant_1',
		messages: [],
		isGenerating: true,
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
		removeQueuedSteeringMessage(messageId) {
			const index = queuedSteeringMessages.findIndex((message) => message.id === messageId)
			if (index >= 0) queuedSteeringMessages.splice(index, 1)
		},
		confirmQueuedSteeringMessage(clientSteeringId, messageId, runId, message) {
			const index = queuedSteeringMessages.findIndex(
				(queued) => queued.id === clientSteeringId
			)
			if (index < 0) return false
			queuedSteeringMessages[index] = {
				...queuedSteeringMessages[index],
				id: messageId,
				clientSteeringId,
				runId,
				content: message?.content ?? queuedSteeringMessages[index].content,
				message: message ?? queuedSteeringMessages[index].message,
				deliveryState: 'queued',
				input: undefined,
			}
			return true
		},
		async flushPendingSteeringMessages() {},
		injectQueuedSteeringMessage(messageId, message, options) {
			if (!message) return false
			const meta = (message.metadata_ ?? {}) as Record<string, unknown>
			const metadata: Record<string, unknown> = { ...meta, steering_state: 'injected' }
			if (options?.runId) metadata.run_id = options.runId
			messageTree.set(messageId, {
				...message,
				id: messageId,
				parent_id: options?.parentId ?? message.parent_id,
				created_at: options?.createdAt ?? message.created_at,
				updated_at: options?.createdAt ?? message.updated_at,
				metadata_: metadata,
			})
			ctx.currentLeafId = messageId
			return true
		},
		setSteeringParentOverride(runId, parentId) {
			steeringParentOverrides.set(runId, parentId)
		},
		consumeSteeringParentOverride(runId) {
			if (!runId) return null
			const parentId = steeringParentOverrides.get(runId) ?? null
			steeringParentOverrides.delete(runId)
			return parentId
		},
		markMessageEntrance(id) {
			messageEntranceIds.add(id)
		},
		consumeMessageEntrance(id) {
			if (!messageEntranceIds.has(id)) return false
			messageEntranceIds.delete(id)
			return true
		},
		messageSkip: 0,
		hasMoreMessages: false,
		isLoadingOlderMessages: false,
		scrollContainer: null,
		autoScroll: true,
		toolTracker: new ToolExecutionTracker(),
		fetchedEventMessageIds: new SvelteSet<string>(),
		eventMessageIdsPending: new SvelteSet<string>(),
		eventsInFlight: false,
		runActivities: new SvelteMap(),
		processRunActivityEvent: vi.fn(),
		citationSources: new SvelteMap(),
		citationTargetMessageId: null,
		addCitationSources() {},
		flushCitationsToMessage() {},
		typingUsers: new SvelteSet<string>(),
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
			return 1
		},
		rebuildRunBlocks: vi.fn(),
		appendStreamingText() {},
		flushStreamingText() {},
		async queueScrollToBottom() {},
		markProgrammaticScroll() {},
	}
	messageTree.set(
		'assistant_1',
		makeApiMessage({ id: 'assistant_1', thread_id: 'thread_1', type: 'assistant' })
	)
	return ctx
}

function dispatch(msg: unknown): void {
	if (!capturedHandler) throw new Error('no handler registered')
	capturedHandler(msg)
}

describe('subscribeToChatEvents', () => {
	afterEach(() => {
		capturedHandler = null
		vi.mocked(isOwnEvent).mockReturnValue(false)
	})

	it('dispatches live run activity events', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'run.activity.started',
				{
					run_id: 'run_1',
					activity_id: 'activity_1',
					activity_type: 'context_compaction',
					title: 'compacting chat',
				},
				{
					id: 'event_1',
					thread_id: 'thread_1',
					message_id: 'message_1',
					created_at: '2026-05-16T10:00:00.000Z',
				}
			)
		)

		expect(ctx.processRunActivityEvent).toHaveBeenCalledWith(
			expect.objectContaining({
				activityId: 'activity_1',
				activityType: 'context_compaction',
				messageId: 'message_1',
				runId: 'run_1',
				status: 'running',
			})
		)
		unsubscribe()
	})

	it('chains injected steering messages when injection arrives before message.created', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		const createdAt = '2026-05-16T10:00:00.000Z'

		dispatch(
			makeStreamMessage(
				'run.steering.injected',
				{
					run_id: 'run_1',
					message_ids: ['queued_1', 'queued_2'],
					parent_id: 'assistant_1',
					steering_injected_at: createdAt,
				},
				{ thread_id: 'thread_1' }
			)
		)

		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'queued_1',
						thread_id: 'thread_1',
						parent_id: 'assistant_1',
						metadata_: { steering_state: 'queued', run_id: 'run_1' },
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)
		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'queued_2',
						thread_id: 'thread_1',
						parent_id: 'assistant_1',
						metadata_: { steering_state: 'queued', run_id: 'run_1' },
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		expect(ctx.messageTree.get('queued_1')?.parent_id).toBe('assistant_1')
		expect(ctx.messageTree.get('queued_2')?.parent_id).toBe('queued_1')
		expect(ctx.messageTree.get('queued_1')?.created_at).toBe(createdAt)
		expect(ctx.messageTree.get('queued_2')?.created_at).toBe(createdAt)
		expect(ctx.consumeSteeringParentOverride('run_1')).toBe('queued_2')
		unsubscribe()
	})

	it('reconciles queued message.created with the optimistic client steering id', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		ctx.stageQueuedSteeringMessage({
			id: 'local-steering-1',
			clientSteeringId: 'local-steering-1',
			runId: 'run_1',
			content: [],
			text: 'steer me',
			attachments: [],
			createdAt: new Date('2026-05-16T10:00:00.000Z'),
			message: null,
			deliveryState: 'sending',
			input: { text: 'steer me' },
		})

		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'server_1',
						thread_id: 'thread_1',
						metadata_: {
							steering_state: 'queued',
							run_id: 'run_1',
							client_steering_id: 'local-steering-1',
						},
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		expect(ctx.queuedSteeringMessages).toHaveLength(1)
		expect(ctx.queuedSteeringMessages[0]).toMatchObject({
			id: 'server_1',
			clientSteeringId: 'local-steering-1',
			deliveryState: 'queued',
		})
		unsubscribe()
	})

	it('re-parents the streaming placeholder onto a user message that wins the WS race', () => {
		const ctx = makeContext()
		// own POST run is in flight with a placeholder still parented at the old
		// leaf, not yet in the tree (SSE message_created has not arrived).
		ctx.streamingAssistant = {
			runId: null,
			messageId: 'pending-assistant',
			content: '',
			timestamp: new Date(),
			senderAgentId: null,
			toolCalls: [],
			isError: false,
			errorMessage: null,
		}
		ctx.streamingAssistantParentId = 'assistant_1'
		vi.mocked(isOwnEvent).mockReturnValue(true)
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'user_new',
						thread_id: 'thread_1',
						type: 'user',
						parent_id: 'assistant_1',
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		// placeholder now hangs off the new user message so it is not flagged
		// as a sibling branch (no "2/2" flash).
		expect(ctx.streamingAssistantParentId).toBe('user_new')
		unsubscribe()
	})
})

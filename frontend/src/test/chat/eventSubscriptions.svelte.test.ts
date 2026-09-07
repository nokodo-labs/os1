import { isOwnEvent } from '$lib/api/sessionId'
import { contentPartsToText } from '$lib/chat/helpers'
import type { ChatSystemEvent } from '$lib/chat/systemEvents'
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
	const systemEvents = new SvelteMap<string, ChatSystemEvent>()
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
		ownsSteeringMessage(messageId) {
			return queuedSteeringMessages.some(
				(message) => message.id === messageId || message.clientSteeringId === messageId
			)
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
			const meta = (message.metadata ?? {}) as Record<string, unknown>
			const metadata: Record<string, unknown> = { ...meta, steering_state: 'injected' }
			if (options?.runId) metadata.run_id = options.runId
			messageTree.set(messageId, {
				...message,
				id: messageId,
				parent_id: options?.parentId ?? message.parent_id,
				created_at: options?.createdAt ?? message.created_at,
				updated_at: options?.createdAt ?? message.updated_at,
				metadata: metadata,
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
		hasNewerMessages: false,
		isLoadingNewerMessages: false,
		branchCursorTowardRoot: null,
		branchCursorTowardLeaf: null,
		initialAnchorMessageId: null,
		siblingCounts: new SvelteMap<string, number>(),
		isLoadingOlderMessages: false,
		scrollContainer: null,
		autoScroll: true,
		measureScrollable: vi.fn(),
		toolTracker: new ToolExecutionTracker(),
		fetchedEventMessageIds: new SvelteSet<string>(),
		eventMessageIdsPending: new SvelteSet<string>(),
		eventsInFlight: false,
		runActivities: new SvelteMap(),
		processRunActivityEvent: vi.fn(),
		runFailures: new SvelteMap(),
		recordRunFailure: vi.fn(),
		systemEvents,
		recordSystemEvent(event) {
			if (systemEvents.has(event.id)) return
			systemEvents.set(event.id, event)
		},
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
						metadata: { steering_state: 'queued', run_id: 'run_1' },
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
						metadata: { steering_state: 'queued', run_id: 'run_1' },
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
			input: { type: 'user', content: [{ type: 'text', text: 'steer me' }] },
		})

		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'server_1',
						thread_id: 'thread_1',
						metadata: {
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

	it('renders a server-owned invocation catch-up as an ordinary message', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		// a mention catch-up writes no steering_state - the user simply wrote
		// the message - and only afterwards names it in a steering event.
		dispatch(
			makeStreamMessage(
				'message.created',
				{ ...makeApiMessage({ id: 'mention_1', thread_id: 'thread_1' }) },
				{ thread_id: 'thread_1' }
			)
		)
		dispatch(
			makeStreamMessage(
				'run.steering.queued',
				{ run_id: 'run_1', message_ids: ['mention_1'], thread_id: 'thread_1' },
				{ thread_id: 'thread_1' }
			)
		)

		// it belongs in the thread, not in the ghost-bubble queue
		expect(ctx.queuedSteeringMessages).toHaveLength(0)
		expect(ctx.messageTree.get('mention_1')).toBeDefined()
		const meta = (ctx.messageTree.get('mention_1')?.metadata ?? {}) as Record<string, unknown>
		expect(meta.steering_state).toBeUndefined()
		unsubscribe()
	})

	it('does not restyle an ordinary message named by a steering event', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		ctx.messageTree.set(
			'mention_1',
			makeApiMessage({ id: 'mention_1', thread_id: 'thread_1', parent_id: 'assistant_1' })
		)

		dispatch(
			makeStreamMessage(
				'run.steering.dropped',
				{
					run_id: 'run_1',
					message_ids: ['mention_1'],
					thread_id: 'thread_1',
				},
				{ thread_id: 'thread_1' }
			)
		)

		// a catch-up is server-authorized and cannot be retracted, so the
		// message must keep rendering normally rather than as dropped steering.
		const meta = (ctx.messageTree.get('mention_1')?.metadata ?? {}) as Record<string, unknown>
		expect(meta.steering_state).toBeUndefined()
		unsubscribe()
	})

	it('does not restyle an ordinary message whose steering events beat message.created', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		const steering = (type: string) =>
			makeStreamMessage(
				type,
				{ run_id: 'run_1', message_ids: ['mention_1'], thread_id: 'thread_1' },
				{ thread_id: 'thread_1' }
			)

		// server-owned catch-up: the run reads the mention before its
		// message.created reaches this client.
		dispatch(steering('run.steering.queued'))
		dispatch(steering('run.steering.injected'))
		dispatch(
			makeStreamMessage(
				'message.created',
				{
					...makeApiMessage({
						id: 'mention_1',
						thread_id: 'thread_1',
						type: 'user',
						parent_id: 'assistant_1',
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		const message = ctx.messageTree.get('mention_1')
		expect(message).toBeDefined()
		const meta = (message?.metadata ?? {}) as Record<string, unknown>
		expect(meta.steering_state).toBeUndefined()
		unsubscribe()
	})

	it('moves displaced traffic after the new run tail on the origin session', () => {
		const ctx = makeContext()
		// the run answered a snapshot that did not include user_late, so the
		// backend spliced assistant_2 in before it and reparented it.
		ctx.messageTree.set(
			'assistant_2',
			makeApiMessage({
				id: 'assistant_2',
				thread_id: 'thread_1',
				type: 'assistant',
				parent_id: 'assistant_1',
			})
		)
		ctx.messageTree.set(
			'user_late',
			makeApiMessage({
				id: 'user_late',
				thread_id: 'thread_1',
				parent_id: 'assistant_1',
				content: [{ type: 'text', text: 'local text' }],
			})
		)
		ctx.currentLeafId = 'assistant_2'
		// this session STARTED the run, so the reparent fans out as its own event.
		vi.mocked(isOwnEvent).mockReturnValue(true)
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'message.updated',
				{
					...makeApiMessage({
						id: 'user_late',
						thread_id: 'thread_1',
						parent_id: 'assistant_2',
						content: [{ type: 'text', text: 'server text' }],
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		const moved = ctx.messageTree.get('user_late')
		expect(moved?.parent_id).toBe('assistant_2')
		// the branch follows the traffic down, so it renders after the run tail
		expect(ctx.currentLeafId).toBe('user_late')
		// own content stays local: the short-circuit still guards the payload merge
		expect(contentPartsToText(moved?.content)).toBe('local text')
		unsubscribe()
	})

	it('moves displaced traffic after the new run tail on another session', () => {
		const ctx = makeContext()
		ctx.messageTree.set(
			'assistant_2',
			makeApiMessage({
				id: 'assistant_2',
				thread_id: 'thread_1',
				type: 'assistant',
				parent_id: 'assistant_1',
			})
		)
		ctx.messageTree.set(
			'user_late',
			makeApiMessage({
				id: 'user_late',
				thread_id: 'thread_1',
				parent_id: 'assistant_1',
				content: [{ type: 'text', text: 'local text' }],
			})
		)
		ctx.currentLeafId = 'assistant_2'
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'message.updated',
				{
					...makeApiMessage({
						id: 'user_late',
						thread_id: 'thread_1',
						parent_id: 'assistant_2',
						content: [{ type: 'text', text: 'server text' }],
					}),
				},
				{ thread_id: 'thread_1' }
			)
		)

		const moved = ctx.messageTree.get('user_late')
		expect(moved?.parent_id).toBe('assistant_2')
		expect(ctx.currentLeafId).toBe('user_late')
		// a foreign update is still authoritative for the payload
		expect(contentPartsToText(moved?.content)).toBe('server text')
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

describe('subscribeToChatEvents - inline system rows', () => {
	afterEach(() => {
		capturedHandler = null
		vi.mocked(isOwnEvent).mockReturnValue(false)
	})

	function accessChange(subjectUserId: string): Record<string, unknown> {
		return {
			resource_type: 'thread',
			resource_id: 'thread_1',
			actor_user_id: 'user_alice',
			revision: 2,
			changes: [
				{
					before: null,
					after: {
						id: 'rule_1',
						subject_user_id: subjectUserId,
						subject_group_id: null,
						subject_role_id: null,
						level: 'editor',
						order_index: 0,
					},
				},
			],
		}
	}

	it('records a membership change the moment it arrives', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage('access.updated', accessChange('user_bob'), {
				id: 'event_acl',
				thread_id: 'thread_1',
				created_at: '2026-01-01T00:00:00.000Z',
			})
		)

		const rows = [...ctx.systemEvents.values()]
		expect(rows).toHaveLength(1)
		expect(rows[0].kind).toBe('member_added')
		expect(rows[0].subjectId).toBe('user_bob')
		unsubscribe()
	})

	it('records an agent joining, anchored to the message it names', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'thread.participants.added',
				{
					thread_id: 'thread_1',
					actor_user_id: 'user_alice',
					actor_name: 'alice',
					kind: 'agent',
					agent_id: 'agent_nova',
					agent_name: 'nova',
				},
				{ id: 'event_agent', thread_id: 'thread_1', message_id: 'assistant_1' }
			)
		)

		const [row] = [...ctx.systemEvents.values()]
		expect(row.kind).toBe('agent_added')
		expect(row.messageId).toBe('assistant_1')
		unsubscribe()
	})

	it('never records a read receipt as a system row', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'thread.participants.updated',
				{
					thread_id: 'thread_1',
					user_id: 'user_bob',
					kind: 'user',
					last_read_message_id: 'assistant_1',
				},
				{ id: 'event_state', thread_id: 'thread_1' }
			)
		)

		expect(ctx.systemEvents.size).toBe(0)
		unsubscribe()
	})

	it('ignores another thread activity', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)

		dispatch(
			makeStreamMessage(
				'access.updated',
				{ ...accessChange('user_bob'), resource_id: 'thread_2' },
				{ id: 'event_other', thread_id: 'thread_2' }
			)
		)

		expect(ctx.systemEvents.size).toBe(0)
		unsubscribe()
	})

	it('keeps the row it already has when the same event arrives twice', () => {
		const ctx = makeContext()
		const unsubscribe = subscribeToChatEvents('thread_1', ctx)
		const event = makeStreamMessage('access.updated', accessChange('user_bob'), {
			id: 'event_acl',
			thread_id: 'thread_1',
		})

		dispatch(event)
		dispatch(event)

		expect(ctx.systemEvents.size).toBe(1)
		unsubscribe()
	})

	it('renders a rename only where a title is shared, and only names the reader', () => {
		const solo = makeContext()
		const soloUnsubscribe = subscribeToChatEvents('thread_1', solo)
		dispatch(
			makeStreamMessage(
				'thread.updated',
				{ id: 'thread_1', title: 'trip' },
				{ id: 'event_rename', thread_id: 'thread_1' }
			)
		)
		expect(solo.systemEvents.size).toBe(0)
		soloUnsubscribe()

		const group = makeContext()
		group.thread = makeThread({
			id: 'thread_1',
			participants: [
				{
					id: 'participant_1',
					thread_id: 'thread_1',
					kind: 'user',
					is_owner: true,
					access_level: 'admin',
					user: { id: 'user_alice', username: 'alice', display_name: 'alice' },
				},
				{
					id: 'participant_2',
					thread_id: 'thread_1',
					kind: 'user',
					is_owner: false,
					access_level: 'editor',
					user: { id: 'user_bob', username: 'bob', display_name: 'bob' },
				},
			],
		})
		vi.mocked(isOwnEvent).mockReturnValue(true)
		const groupUnsubscribe = subscribeToChatEvents('thread_1', group)

		dispatch(
			makeStreamMessage(
				'thread.updated',
				{ id: 'thread_1', title: 'trip' },
				{ id: 'event_rename', thread_id: 'thread_1' }
			)
		)

		const [row] = [...group.systemEvents.values()]
		expect(row.kind).toBe('title_changed')
		expect(row.title).toBe('trip')
		expect(row.actorUserId).toBe(group.currentUserId)
		groupUnsubscribe()
	})
})

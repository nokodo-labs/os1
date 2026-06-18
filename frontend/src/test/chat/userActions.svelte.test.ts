import type { ApiMessage, ChatContext, QueuedSteeringMessage } from '$lib/chat/types'
import { handleSendMessage } from '$lib/chat/userActions'
import { ToolExecutionTracker } from '$lib/tools'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

const activeRunsMocks = vi.hoisted(() => ({
	getRunsForThread: vi.fn(),
}))

const steeringMocks = vi.hoisted(() => ({
	steerRun: vi.fn(),
}))

const streamProcessorMocks = vi.hoisted(() => ({
	runThreadStream: vi.fn(),
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn(),
		POST: vi.fn(),
		PATCH: vi.fn(),
		DELETE: vi.fn(),
	},
}))

vi.mock('$lib/chat/steering', () => ({
	steerRun: steeringMocks.steerRun,
}))

vi.mock('$lib/chat/streamProcessor', () => ({
	runThreadStream: streamProcessorMocks.runThreadStream,
}))

vi.mock('$lib/chat/dataLoader', () => ({
	syncCacheAfterRun: vi.fn(),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		getRunsForThread: activeRunsMocks.getRunsForThread,
	},
}))

vi.mock('$lib/stores/agents.svelte', () => ({
	agents: {
		get: vi.fn(() => ({ config: { features: { steering: { enabled: true } } } })),
	},
}))

vi.mock('$lib/stores/selectedAgent.svelte', () => ({
	selectedAgent: { id: 'agent_1' },
}))

function makeContext(overrides: Partial<ChatContext> = {}): ChatContext {
	const staged: QueuedSteeringMessage[] = []
	const messageTree = new SvelteMap<string, ApiMessage>()
	const base: ChatContext = {
		thread: makeThread({ id: 'thread_1' }),
		messageTree,
		messageChildren: new Map(),
		currentLeafId: null,
		messages: [],
		isGenerating: true,
		activeRun: 1,
		streamingAssistant: null,
		streamingAssistantParentId: null,
		streamingLeafId: null,
		viewingStreamingBranch: true,
		optimisticUserMessage: null,
		pendingStreamSessionId: null,
		queuedSteeringMessages: staged,
		lastRunInput: '',
		inputValue: 'steer me',
		runAbortController: null,
		stageQueuedSteeringMessage(message) {
			staged.push(message)
		},
		removeQueuedSteeringMessage(messageId) {
			const index = staged.findIndex((message) => message.id === messageId)
			if (index >= 0) staged.splice(index, 1)
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
		processRunActivityEvent() {},
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
		rebuildRunBlocks() {},
		async queueScrollToBottom() {},
	}
	return { ...base, ...overrides }
}

describe('handleSendMessage steering', () => {
	beforeEach(() => {
		resetIdCounter()
		activeRunsMocks.getRunsForThread.mockReset()
		steeringMocks.steerRun.mockReset()
		streamProcessorMocks.runThreadStream.mockReset()
		activeRunsMocks.getRunsForThread.mockReturnValue([
			{ threadId: 'thread_1', runId: 'run_1', agentId: 'agent_1', startedAt: 1 },
		])
	})

	it('uses the stable streaming parent instead of the placeholder as steering parent', async () => {
		const flushPendingSteeringMessages = vi.fn()
		const parentMessage = makeApiMessage({ id: 'parent_1', thread_id: 'thread_1' })
		const streamingMessage = makeApiMessage({
			id: 'assistant_local',
			thread_id: 'thread_1',
			type: 'assistant',
			parent_id: 'parent_1',
			content: [],
			sender_agent_id: 'agent_1',
		})
		const ctx = makeContext({
			currentLeafId: 'assistant_local',
			flushPendingSteeringMessages,
			streamingLeafId: 'assistant_local',
			streamingAssistantParentId: 'parent_1',
			streamingAssistant: {
				runId: 'run_1',
				messageId: 'assistant_local',
				content: 'partial',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: false,
				errorMessage: null,
			},
		})
		ctx.messageTree.set(parentMessage.id, parentMessage)
		ctx.messageTree.set(streamingMessage.id, streamingMessage)

		await handleSendMessage('steer me', ctx)

		expect(steeringMocks.steerRun).not.toHaveBeenCalled()
		expect(flushPendingSteeringMessages).toHaveBeenCalledWith('run_1', 'parent_1')
		expect(ctx.inputValue).toBe('')
		expect(ctx.queuedSteeringMessages).toHaveLength(1)
		expect(ctx.queuedSteeringMessages[0]).toMatchObject({
			runId: 'run_1',
			deliveryState: 'sending',
			text: 'steer me',
		})
		expect(ctx.queuedSteeringMessages[0].clientSteeringId).toBe(
			ctx.queuedSteeringMessages[0].id
		)
	})

	it('keeps a known persisted leaf as the steering parent', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const flushPendingSteeringMessages = vi.fn()
		const ctx = makeContext({
			currentLeafId: persistedMessage.id,
			flushPendingSteeringMessages,
		})
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('steer me', ctx)

		expect(flushPendingSteeringMessages).toHaveBeenCalledWith('run_1', 'message_1')
	})

	it('parents later queued steering messages to the previous queued message', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const flushParents: (string | null)[] = []
		let queuedIndex = 0
		const ctx = makeContext({
			currentLeafId: persistedMessage.id,
			async flushPendingSteeringMessages(_runId, parentId) {
				flushParents.push(parentId)
				const pending = ctx.queuedSteeringMessages.find(
					(message) => message.deliveryState === 'sending'
				)
				if (!pending) return
				ctx.removeQueuedSteeringMessage(pending.id)
				queuedIndex += 1
				ctx.stageQueuedSteeringMessage({
					...pending,
					id: `queued_${queuedIndex}`,
					runId: 'run_1',
					deliveryState: 'queued',
					input: undefined,
				})
			},
		})
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('first steer', ctx)
		await handleSendMessage('second steer', ctx)

		expect(flushParents).toEqual(['message_1', 'queued_1'])
	})

	it('queues steering during a run before the active run store catches up', async () => {
		activeRunsMocks.getRunsForThread.mockReturnValue([])
		const flushPendingSteeringMessages = vi.fn()
		const ctx = makeContext({
			flushPendingSteeringMessages,
			optimisticUserMessage: null,
			streamingAssistant: {
				runId: null,
				messageId: 'pending-regen',
				content: '',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: false,
				errorMessage: null,
			},
		})

		await handleSendMessage('steer while regen starts', ctx)

		expect(flushPendingSteeringMessages).not.toHaveBeenCalled()
		expect(ctx.queuedSteeringMessages).toHaveLength(1)
		expect(ctx.queuedSteeringMessages[0]).toMatchObject({
			runId: '',
			deliveryState: 'sending',
			text: 'steer while regen starts',
		})
	})

	it('starts a new run instead of steering against a stale active run', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: persistedMessage.id,
		})
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('new message after run settled', ctx)

		expect(ctx.queuedSteeringMessages).toHaveLength(0)
		expect(streamProcessorMocks.runThreadStream).toHaveBeenCalledWith(
			expect.objectContaining({
				threadId: 'thread_1',
				agentId: 'agent_1',
				parentId: 'message_1',
				input: { text: 'new message after run settled' },
			}),
			ctx
		)
	})
})

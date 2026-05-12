import type { RunInput } from '$lib/api/streaming'
import { handleSendMessage } from '$lib/chat/userActions'
import type { ApiMessage, ChatContext, QueuedSteeringMessage } from '$lib/chat/types'
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
	runThreadStream: vi.fn(),
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
		fetchedToolEventMessageIds: new SvelteSet<string>(),
		toolEventsPendingIds: new SvelteSet<string>(),
		toolEventsInFlight: false,
		confirmDeleteMessage: null,
		isDeletingMessage: false,
		deleteMessageError: null,
		pendingActions: new SvelteMap<string, 'reveal' | 'reference'>(),
		attachmentStates: new SvelteMap(),
		threadAttachments: [],
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
		activeRunsMocks.getRunsForThread.mockReturnValue([
			{ threadId: 'thread_1', runId: 'run_1', agentId: 'agent_1', startedAt: 1 },
		])
		steeringMocks.steerRun.mockResolvedValue({ messageId: 'queued_1', state: 'queued' })
	})

	it('does not send a streaming placeholder as the steering parent', async () => {
		const streamingMessage = makeApiMessage({
			id: 'assistant_local',
			thread_id: 'thread_1',
			type: 'assistant',
			content: [],
			sender_agent_id: 'agent_1',
		})
		const ctx = makeContext({
			currentLeafId: 'assistant_local',
			streamingLeafId: 'assistant_local',
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
		ctx.messageTree.set(streamingMessage.id, streamingMessage)

		await handleSendMessage('steer me', ctx)

		expect(steeringMocks.steerRun).toHaveBeenCalledWith(
			'run_1',
			expect.objectContaining<Partial<RunInput>>({ text: 'steer me' }),
			null
		)
		expect(ctx.inputValue).toBe('')
		expect(ctx.queuedSteeringMessages).toHaveLength(1)
	})

	it('keeps a known persisted leaf as the steering parent', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({ currentLeafId: persistedMessage.id })
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('steer me', ctx)

		expect(steeringMocks.steerRun).toHaveBeenCalledWith(
			'run_1',
			expect.objectContaining<Partial<RunInput>>({ text: 'steer me' }),
			'message_1'
		)
	})
})

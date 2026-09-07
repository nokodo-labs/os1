import type {
	ApiMessage,
	ChatContext,
	PendingAttachment,
	QueuedSteeringMessage,
	RunModifiers,
} from '$lib/chat/types'
import {
	deleteUserMessage,
	handleRegenerateMessage,
	handleSaveEditMessage,
	handleSendMessage,
	handleStopGeneration,
	requestDeleteUserMessage,
} from '$lib/chat/userActions'
import type { Thread } from '$lib/stores/chat.svelte'
import { modals } from '$lib/stores/modals.svelte'
import { ToolExecutionTracker } from '$lib/tools'
import { SvelteMap, SvelteSet } from 'svelte/reactivity'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage, makeThread, resetIdCounter } from './fixtures'

const activeRunsMocks = vi.hoisted(() => ({
	getRunsForThread: vi.fn(),
	forgetRun: vi.fn(),
}))

const apiMocks = vi.hoisted(() => ({
	del: vi.fn(),
	patch: vi.fn(),
	post: vi.fn(),
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
		POST: apiMocks.post,
		PATCH: apiMocks.patch,
		DELETE: apiMocks.del,
	},
}))

vi.mock('$lib/chat/steering', () => ({
	steerRun: steeringMocks.steerRun,
}))

vi.mock('$lib/chat/streamProcessor', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/chat/streamProcessor')>()),
	runThreadStream: streamProcessorMocks.runThreadStream,
}))

vi.mock('$lib/chat/dataLoader', () => ({
	syncCacheAfterRun: vi.fn(),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		getRunsForThread: activeRunsMocks.getRunsForThread,
		forgetRun: activeRunsMocks.forgetRun,
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
		ownsSteeringMessage(messageId) {
			return staged.some(
				(message) => message.id === messageId || message.clientSteeringId === messageId
			)
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
		appendStreamingText() {},
		flushStreamingText() {},
		markProgrammaticScroll() {},
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
		runFailures: new SvelteMap(),
		recordRunFailure() {},
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
				splice: { parent_id: 'message_1' },
				input: {
					type: 'user',
					content: [{ type: 'text', text: 'new message after run settled' }],
				},
			}),
			ctx
		)
	})

	it('sends a reply as a semantic anchor without changing tree placement', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const olderMessage = makeApiMessage({ id: 'message_0', thread_id: 'thread_1' })
		const ctx = makeContext({
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: persistedMessage.id,
		})
		ctx.messageTree.set(olderMessage.id, olderMessage)
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('answering the older one', ctx, {
			webSearch: false,
			thinkLonger: false,
			generateImage: false,
			extraPlugins: [],
			attachments: [],
			replyToMessageId: 'message_0',
		})

		const call = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.input.reply_to_message_id).toBe('message_0')
		// the reply anchor must NOT move the message in the tree: placement stays
		// the normal continuation from the current leaf.
		expect(call.splice).toEqual({ parent_id: 'message_1' })
	})

	it('starts a new run instead of queueing behind a run that already failed', async () => {
		const persistedMessage = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			isGenerating: false,
			currentLeafId: persistedMessage.id,
			// a failed run keeps its streamingAssistant so the error bubble
			// stays rendered - that must not read as a live run.
			streamingAssistant: {
				runId: 'run_dead',
				messageId: 'error-1',
				content: '',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: true,
				errorMessage: 'boom',
			},
		})
		ctx.messageTree.set(persistedMessage.id, persistedMessage)

		await handleSendMessage('after the failure', ctx)

		expect(ctx.queuedSteeringMessages).toHaveLength(0)
		expect(streamProcessorMocks.runThreadStream).toHaveBeenCalled()
	})

	it('retries a failed run at the exact message it failed on', async () => {
		const anchor = makeApiMessage({ id: 'anchor_1', thread_id: 'thread_1' })
		const newerLeaf = makeApiMessage({ id: 'leaf_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			isGenerating: false,
			streamingAssistant: null,
			// the view has moved on, but a retry must ignore that
			currentLeafId: newerLeaf.id,
		})
		ctx.messageTree.set(anchor.id, anchor)
		ctx.messageTree.set(newerLeaf.id, newerLeaf)

		await handleRegenerateMessage('anchor_1', ctx, null, 'agent_9')

		const call = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0]
		// no input: the splice then places the run's OWN output, as a sibling of
		// the failed attempt on the very message it failed to answer.
		expect(call.input).toBeNull()
		expect(call.splice).toEqual({ parent_id: 'anchor_1' })
		// and it must re-run the agent that failed, not the composer's selection
		expect(call.agentId).toBe('agent_9')
	})
})

describe('runs after a failed run', () => {
	beforeEach(() => {
		resetIdCounter()
		apiMocks.post.mockReset()
		apiMocks.post.mockResolvedValue({ data: { ok: true }, error: undefined })
		activeRunsMocks.forgetRun.mockReset()
		activeRunsMocks.getRunsForThread.mockReset()
		activeRunsMocks.getRunsForThread.mockReturnValue([])
		streamProcessorMocks.runThreadStream.mockReset()
	})

	/**
	 * the state a run leaves behind when it dies: its own placeholder sits in
	 * the tree so the bubble keeps rendering, and every leaf pointer names it.
	 */
	function makeFailedRunContext(): ChatContext {
		const persisted = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			thread: makeThread({ id: 'thread_1', current_message_id: 'message_1' }),
			isGenerating: false,
			currentLeafId: 'pending-3',
			streamingAssistantParentId: 'pending-3',
			streamingLeafId: null,
			optimisticUserMessage: null,
			streamingAssistant: {
				runId: null,
				messageId: 'error-3',
				content: '',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: true,
				errorMessage: 'boom',
			},
		})
		ctx.messageTree.set(persisted.id, persisted)
		ctx.messageTree.set(
			'pending-3',
			makeApiMessage({
				id: 'pending-3',
				thread_id: 'thread_1',
				type: 'assistant',
				parent_id: 'message_1',
				content: [],
				sender_agent_id: 'agent_1',
			})
		)
		return ctx
	}

	it('never splices onto the placeholder a dead run left in the tree', async () => {
		// the backend parses a splice parent as a typeid, so `pending-3` is a
		// 422 - and the leaf keeps pointing at it, so every later run repeats it.
		await handleRegenerateMessage(null, makeFailedRunContext())

		const call = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.splice).toEqual({ parent_id: 'message_1' })
	})

	it('ignores a placeholder passed as the retry anchor', async () => {
		await handleRegenerateMessage('pending-3', makeFailedRunContext())

		const call = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.splice).toEqual({ parent_id: 'message_1' })
	})

	it('sends the next message against a real parent, not the dead placeholder', async () => {
		await handleSendMessage('after the failure', makeFailedRunContext())

		const call = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0]
		expect(call.splice).toEqual({ parent_id: 'message_1' })
	})
})

describe('a regeneration that fails', () => {
	beforeEach(() => {
		resetIdCounter()
		activeRunsMocks.getRunsForThread.mockReset()
		activeRunsMocks.getRunsForThread.mockReturnValue([])
		streamProcessorMocks.runThreadStream.mockReset()
		streamProcessorMocks.runThreadStream.mockRejectedValue(new Error('provider is down'))
	})

	function makeBranchedContext(): ChatContext {
		const anchor = makeApiMessage({ id: 'anchor_1', thread_id: 'thread_1' })
		const answer = makeApiMessage({
			id: 'answer_1',
			thread_id: 'thread_1',
			type: 'assistant',
			parent_id: 'anchor_1',
			content: [{ type: 'text', text: 'first answer' }],
			sender_agent_id: 'agent_1',
		})
		const ctx = makeContext({
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: 'answer_1',
		})
		ctx.messageTree.set(anchor.id, anchor)
		ctx.messageTree.set(answer.id, answer)
		return ctx
	}

	it('goes back to the answer it moved off, so the switcher survives', async () => {
		const ctx = makeBranchedContext()

		await handleRegenerateMessage('anchor_1', ctx)

		// parked on the anchor the retry never answered, the previous answer is
		// off-branch and nothing renders a way back to it.
		expect(ctx.currentLeafId).toBe('answer_1')
	})

	it('writes no empty placeholder message for a run that produced nothing', async () => {
		const ctx = makeBranchedContext()

		await handleRegenerateMessage('anchor_1', ctx)

		const ids = [...ctx.messageTree.keys()]
		expect(ids).toEqual(['anchor_1', 'answer_1'])
	})
})

describe('handleStopGeneration', () => {
	beforeEach(() => {
		resetIdCounter()
		apiMocks.post.mockReset()
		apiMocks.post.mockResolvedValue({ data: { ok: true }, error: undefined })
		activeRunsMocks.forgetRun.mockReset()
	})

	it('drops the run from the global store so nothing re-joins it', async () => {
		const ctx = makeContext({
			streamingAssistant: {
				runId: 'run_1',
				messageId: 'pending-1',
				content: '',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: false,
				errorMessage: null,
			},
		})

		await handleStopGeneration(ctx)

		// the page resumes any run the store still lists, and it wakes exactly
		// when isGenerating drops - which is what stopping does.
		expect(activeRunsMocks.forgetRun).toHaveBeenCalledWith('run_1')
		expect(ctx.streamingAssistant).toBeNull()
		expect([...ctx.messageTree.keys()]).toEqual([])
	})

	it('still keeps whatever text had already streamed', async () => {
		// text only ever streams into the message the backend reserved, so the
		// bubble is already on a real id by the time anyone can stop it
		const ctx = makeContext({
			streamingAssistantParentId: 'message_1',
			streamingAssistant: {
				runId: 'run_1',
				messageId: 'assistant_1',
				content: 'half an answer',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: false,
				errorMessage: null,
			},
		})

		await handleStopGeneration(ctx)

		const kept = ctx.messageTree.get('assistant_1')
		expect(kept?.content).toEqual([{ type: 'text', text: 'half an answer' }])
		expect(kept?.metadata?.partial).toBe(true)
	})

	it('never writes a bridge placeholder into the tree', async () => {
		const ctx = makeContext({
			streamingAssistantParentId: 'message_1',
			streamingAssistant: {
				runId: 'run_1',
				messageId: 'pending-1',
				content: 'half an answer',
				timestamp: new Date(),
				senderAgentId: 'agent_1',
				toolCalls: [],
				isError: false,
				errorMessage: null,
			},
		})

		await handleStopGeneration(ctx)

		// the backend cannot resolve `pending-1`, so a leaf on it 422s every
		// later run on this branch
		expect([...ctx.messageTree.keys()]).toEqual([])
		expect(ctx.streamingLeafId).toBeNull()
	})
})

describe('user message delete', () => {
	beforeEach(() => {
		resetIdCounter()
		apiMocks.del.mockReset()
		apiMocks.del.mockResolvedValue({ response: { ok: true }, error: undefined })
		modals.close()
	})

	function makeDeletableContext(): ChatContext {
		const message = makeApiMessage({ id: 'msg_1', thread_id: 'thread_1' })
		const ctx = makeContext({ messages: [message], currentLeafId: message.id })
		ctx.messageTree.set(message.id, message)
		return ctx
	}

	it('offers the originated-resources opt-in, off by default', () => {
		requestDeleteUserMessage('msg_1', makeDeletableContext())

		expect(modals.confirmDeletePayload?.toggle?.label).toBeTruthy()
		expect(modals.confirmDeletePayload?.toggle?.default ?? false).toBe(false)
	})

	it('forwards the opt-in as a query param when the switch is on', async () => {
		requestDeleteUserMessage('msg_1', makeDeletableContext())

		await modals.confirmDeletePayload?.onDelete(true)

		const params = apiMocks.del.mock.calls.at(-1)?.[1].params
		expect(params.query).toEqual({ delete_originated_resources: true })
	})

	it('omits the query param when the opt-in stays off', async () => {
		await deleteUserMessage('msg_1', makeDeletableContext())

		const params = apiMocks.del.mock.calls.at(-1)?.[1].params
		expect(params.query).toBeUndefined()
	})
})

describe('handleSendMessage in multi-writer threads', () => {
	type Participant = NonNullable<Thread['participants']>[number]
	function writer(id: string, is_owner = false): Participant {
		return {
			id: `p_${id}`,
			thread_id: 'thread_1',
			access_level: 'editor',
			is_owner,
			kind: 'user',
			user: { id },
		}
	}

	beforeEach(() => {
		resetIdCounter()
		apiMocks.post.mockReset()
		steeringMocks.steerRun.mockReset()
		streamProcessorMocks.runThreadStream.mockReset()
		activeRunsMocks.getRunsForThread.mockReturnValue([
			{ threadId: 'thread_1', runId: 'run_1', agentId: 'agent_1', startedAt: 1 },
		])
	})

	it('only sends: no run and no steering, even with an agent selected and a run live', async () => {
		const leaf = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const posted = makeApiMessage({
			id: 'message_2',
			thread_id: 'thread_1',
			type: 'user',
			parent_id: leaf.id,
		})
		apiMocks.post.mockResolvedValue({
			data: posted,
			error: undefined,
			response: { status: 201 },
		})
		const ctx = makeContext({
			thread: makeThread({
				id: 'thread_1',
				participants: [writer('user_1', true), writer('user_2')],
			}),
			isGenerating: true,
			currentLeafId: leaf.id,
		})
		ctx.messageTree.set(leaf.id, leaf)

		await handleSendMessage('hello all', ctx, {
			webSearch: false,
			thinkLonger: false,
			generateImage: false,
			extraPlugins: [],
			attachments: [],
		})

		expect(apiMocks.post).toHaveBeenCalledTimes(1)
		expect(apiMocks.post.mock.calls[0][0]).toBe('/v1/threads/{thread_id}/messages')
		expect(streamProcessorMocks.runThreadStream).not.toHaveBeenCalled()
		expect(steeringMocks.steerRun).not.toHaveBeenCalled()
		expect(ctx.queuedSteeringMessages).toHaveLength(0)
	})

	it('runs the armed agent with the message as input, and posts nothing', async () => {
		const leaf = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			thread: makeThread({
				id: 'thread_1',
				participants: [writer('user_1', true), writer('user_2')],
			}),
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: leaf.id,
		})
		ctx.messageTree.set(leaf.id, leaf)

		await handleSendMessage('what do you think?', ctx, {
			webSearch: false,
			thinkLonger: false,
			generateImage: false,
			extraPlugins: [],
			attachments: [],
			// armed explicitly by the user - NOT the composer's global selection
			invokeAgentId: 'agent_7',
		})

		expect(apiMocks.post).not.toHaveBeenCalled()
		expect(steeringMocks.steerRun).not.toHaveBeenCalled()
		expect(ctx.queuedSteeringMessages).toHaveLength(0)
		expect(streamProcessorMocks.runThreadStream).toHaveBeenCalledTimes(1)
		expect(streamProcessorMocks.runThreadStream).toHaveBeenCalledWith(
			expect.objectContaining({
				threadId: 'thread_1',
				agentId: 'agent_7',
				splice: { parent_id: 'message_1' },
				input: {
					type: 'user',
					content: [{ type: 'text', text: 'what do you think?' }],
				},
			}),
			ctx
		)
	})

	it('ignores a live run and never steers when an agent is armed', async () => {
		const leaf = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			thread: makeThread({
				id: 'thread_1',
				participants: [writer('user_1', true), writer('user_2')],
			}),
			// a run is live and the active-run store knows about it
			isGenerating: true,
			currentLeafId: leaf.id,
		})
		ctx.messageTree.set(leaf.id, leaf)

		await handleSendMessage('you too', ctx, {
			webSearch: false,
			thinkLonger: false,
			generateImage: false,
			extraPlugins: [],
			attachments: [],
			invokeAgentId: 'agent_7',
		})

		expect(ctx.queuedSteeringMessages).toHaveLength(0)
		expect(steeringMocks.steerRun).not.toHaveBeenCalled()
		expect(streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0].agentId).toBe('agent_7')
	})
})

describe('originated resources on send', () => {
	function attachment(overrides: Partial<PendingAttachment> = {}): PendingAttachment {
		return {
			fileId: 'file_1',
			resourceType: 'file',
			filename: 'shot.png',
			mediaType: 'image/png',
			category: 'image',
			source: 'upload',
			...overrides,
		}
	}

	function modifiers(attachments: PendingAttachment[]): RunModifiers {
		return {
			webSearch: false,
			thinkLonger: false,
			generateImage: false,
			extraPlugins: [],
			attachments,
		}
	}

	beforeEach(() => {
		resetIdCounter()
		apiMocks.post.mockReset()
		streamProcessorMocks.runThreadStream.mockReset()
		activeRunsMocks.getRunsForThread.mockReturnValue([])
	})

	function makeIdleContext(): ChatContext {
		const leaf = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		const ctx = makeContext({
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: leaf.id,
		})
		ctx.messageTree.set(leaf.id, leaf)
		return ctx
	}

	it('originates what the composer uploaded, never what it picked', async () => {
		const ctx = makeIdleContext()

		await handleSendMessage(
			'look at this',
			ctx,
			modifiers([
				attachment(),
				attachment({
					fileId: 'note_1',
					resourceType: 'note',
					filename: 'groceries',
					source: 'resource',
				}),
			])
		)

		const input = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0].input
		expect(input.attachments).toEqual([
			{ type: 'file', id: 'file_1' },
			{ type: 'note', id: 'note_1' },
		])
		// the picked note already existed - attaching it must not claim it.
		expect(input.originated_resources).toEqual([{ type: 'file', id: 'file_1' }])
	})

	it('omits originated_resources when nothing was created for the message', async () => {
		const ctx = makeIdleContext()

		await handleSendMessage(
			'remember this one',
			ctx,
			modifiers([attachment({ fileId: 'note_1', resourceType: 'note', source: 'resource' })])
		)

		const input = streamProcessorMocks.runThreadStream.mock.calls.at(-1)?.[0].input
		expect(input.attachments).toEqual([{ type: 'note', id: 'note_1' }])
		expect(input.originated_resources).toBeUndefined()
	})

	it('marks provenance on a plain conversation post too', async () => {
		const leaf = makeApiMessage({ id: 'message_1', thread_id: 'thread_1' })
		apiMocks.post.mockResolvedValue({
			data: makeApiMessage({ id: 'message_2', thread_id: 'thread_1', parent_id: leaf.id }),
			error: undefined,
			response: { status: 201 },
		})
		const ctx = makeContext({
			thread: makeThread({
				id: 'thread_1',
				participants: [
					{
						id: 'p_user_1',
						thread_id: 'thread_1',
						access_level: 'editor',
						is_owner: true,
						kind: 'user',
						user: { id: 'user_1' },
					},
					{
						id: 'p_user_2',
						thread_id: 'thread_1',
						access_level: 'editor',
						is_owner: false,
						kind: 'user',
						user: { id: 'user_2' },
					},
				],
			}),
			isGenerating: false,
			streamingAssistant: null,
			currentLeafId: leaf.id,
		})
		ctx.messageTree.set(leaf.id, leaf)

		await handleSendMessage('here it is', ctx, modifiers([attachment()]))

		const body = apiMocks.post.mock.calls.at(-1)?.[1].body
		expect(body.originated_resources).toEqual([{ type: 'file', id: 'file_1' }])
	})
})

describe('handleSaveEditMessage', () => {
	beforeEach(() => {
		resetIdCounter()
		apiMocks.patch.mockReset()
	})

	function makeEditableContext(): ChatContext {
		const message = makeApiMessage({
			id: 'msg_1',
			thread_id: 'thread_1',
			content: [{ type: 'text', text: 'first draft' }],
		})
		const ctx = makeContext({ messages: [message], currentLeafId: message.id })
		ctx.messageTree.set(message.id, message)
		return ctx
	}

	it('sends the changed content and leaves attachments untouched', async () => {
		const ctx = makeEditableContext()
		apiMocks.patch.mockResolvedValue({
			data: makeApiMessage({
				id: 'msg_1',
				thread_id: 'thread_1',
				content: [{ type: 'text', text: 'second draft' }],
			}),
			error: undefined,
		})

		await handleSaveEditMessage('msg_1', 'second draft', ctx)

		const body = apiMocks.patch.mock.calls.at(-1)?.[1].body
		expect(body).toEqual({ content: 'second draft' })
		// omitting the key keeps the existing links; sending them back would
		// replace every one of them along with the access they grant.
		expect(body.attachments).toBeUndefined()
	})

	it('does not patch a message whose text did not change', async () => {
		await handleSaveEditMessage('msg_1', 'first draft', makeEditableContext())

		expect(apiMocks.patch).not.toHaveBeenCalled()
	})
})

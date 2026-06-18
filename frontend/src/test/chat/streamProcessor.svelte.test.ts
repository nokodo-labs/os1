import { StreamHttpError, type ChatStreamDelta } from '$lib/api/streaming/chatStream'
import {
	consumeStream,
	processDelta,
	reconcileStreamedContent,
	RunFailedError,
	runThreadStream,
} from '$lib/chat/streamProcessor'
import type { ChatContext, StreamDeltaContext } from '$lib/chat/types'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { makeApiMessage } from './fixtures'

const activeRunsMocks = vi.hoisted(() => ({
	forgetRun: vi.fn(),
	refresh: vi.fn(async () => {}),
	getRunsForThread: vi.fn(() => [] as { runId: string }[]),
}))

vi.mock('$lib/stores/activeRuns.svelte', () => ({
	activeRunsStore: {
		forgetRun: activeRunsMocks.forgetRun,
		refresh: activeRunsMocks.refresh,
		getRunsForThread: activeRunsMocks.getRunsForThread,
	},
}))

const streamMocks = vi.hoisted(() => ({
	runChatStream: vi.fn(),
	resumeRunStream: vi.fn(),
}))

vi.mock('$lib/api/streaming/chatStream', async (importOriginal) => {
	const actual = await importOriginal<typeof import('$lib/api/streaming/chatStream')>()
	return {
		...actual,
		runChatStream: streamMocks.runChatStream,
		resumeRunStream: streamMocks.resumeRunStream,
	}
})

vi.mock('$lib/utils/haptics', () => ({
	hapticFeedback: vi.fn(),
	throttledHapticFeedback: vi.fn(),
}))

function makeDelta(message = makeApiMessage()) {
	return {
		event: 'message_created',
		data: message,
	} as Parameters<typeof processDelta>[0]
}

describe('processDelta steering reconciliation', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
	})

	it('confirms queued steering messages by client id from SSE message.created', () => {
		const confirmQueuedSteeringMessage = vi.fn(() => true)
		const stageQueuedSteeringMessage = vi.fn()
		const ctx = {
			confirmQueuedSteeringMessage,
			stageQueuedSteeringMessage,
		} as unknown as ChatContext
		const msg = makeApiMessage({
			id: 'msg_server_1',
			type: 'user',
			metadata_: {
				steering_state: 'queued',
				run_id: 'run_1',
				client_steering_id: 'local-steering-1',
			},
		})

		const result = processDelta(makeDelta(msg), {} as StreamDeltaContext, ctx)

		expect(result).toBe('continue')
		expect(confirmQueuedSteeringMessage).toHaveBeenCalledWith(
			'local-steering-1',
			'msg_server_1',
			'run_1',
			msg
		)
		expect(stageQueuedSteeringMessage).not.toHaveBeenCalled()
	})

	it('stages queued steering messages when SSE has no matching client id', () => {
		const confirmQueuedSteeringMessage = vi.fn(() => false)
		const stageQueuedSteeringMessage = vi.fn()
		const ctx = {
			confirmQueuedSteeringMessage,
			stageQueuedSteeringMessage,
		} as unknown as ChatContext
		const msg = makeApiMessage({
			id: 'msg_server_2',
			type: 'user',
			metadata_: {
				steering_state: 'queued',
				run_id: 'run_1',
			},
		})

		processDelta(makeDelta(msg), {} as StreamDeltaContext, ctx)

		expect(confirmQueuedSteeringMessage).not.toHaveBeenCalled()
		expect(stageQueuedSteeringMessage).toHaveBeenCalledWith(
			expect.objectContaining({ id: 'msg_server_2', runId: 'run_1', message: msg })
		)
	})

	it('forgets the active run when the stream emits the agent done sentinel', () => {
		const ctx = {} as ChatContext

		const result = processDelta(
			{
				event: 'delta',
				data: {
					run_id: 'run_done',
					agent_id: 'agent_1',
					message_id: null,
					parent_id: null,
					delta: { done: true },
				},
			},
			{} as StreamDeltaContext,
			ctx
		)

		expect(result).toBe('done')
		expect(activeRunsMocks.forgetRun).toHaveBeenCalledWith('run_done')
	})

	it('forgets the active run when the stream emits an error', () => {
		const ctx = {} as ChatContext

		expect(() =>
			processDelta(
				{
					event: 'error',
					data: { run_id: 'run_failed', message: 'generation failed' },
				},
				{} as StreamDeltaContext,
				ctx
			)
		).toThrow('generation failed')
		expect(activeRunsMocks.forgetRun).toHaveBeenCalledWith('run_failed')
	})
})

async function* asyncFrom(
	frames: ChatStreamDelta[]
): AsyncGenerator<ChatStreamDelta, void, unknown> {
	for (const f of frames) yield f
}

const doneFrame: ChatStreamDelta = {
	event: 'delta',
	data: {
		run_id: 'run_x',
		agent_id: 'agent_1',
		message_id: null,
		parent_id: null,
		delta: { done: true },
	},
} as unknown as ChatStreamDelta

function makeConsumeCtx(activeRun: number): ChatContext {
	return {
		activeRun,
		streamingAssistantParentId: null,
		runAbortController: new AbortController(),
		appendStreamingText: () => {},
		flushStreamingText: () => {},
	} as unknown as ChatContext
}

describe('consumeStream outcomes', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
	})

	it("returns 'ended' when the generator exhausts without a terminal event", async () => {
		const ctx = makeConsumeCtx(1)
		const outcome = await consumeStream(
			asyncFrom([]),
			{ runId: 1, threadId: 'thread_1', parentId: null },
			ctx
		)
		expect(outcome).toBe('ended')
	})

	it("returns 'done' when a terminal done sentinel is processed", async () => {
		const ctx = makeConsumeCtx(1)
		const outcome = await consumeStream(
			asyncFrom([doneFrame]),
			{ runId: 1, threadId: 'thread_1', parentId: null },
			ctx
		)
		expect(outcome).toBe('done')
	})

	it("returns 'superseded' when the active run changes mid-stream", async () => {
		const ctx = makeConsumeCtx(2)
		const outcome = await consumeStream(
			asyncFrom([doneFrame]),
			{ runId: 1, threadId: 'thread_1', parentId: null },
			ctx
		)
		expect(outcome).toBe('superseded')
		expect(ctx.runAbortController?.signal.aborted).toBe(true)
	})
})

describe('RunFailedError', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
	})

	it('is thrown (not a plain Error) on a stream error event so callers can skip resume', () => {
		const ctx = {} as ChatContext
		expect(() =>
			processDelta(
				{ event: 'error', data: { run_id: 'run_e', message: 'boom' } },
				{} as StreamDeltaContext,
				ctx
			)
		).toThrow(RunFailedError)
	})
})

describe('reconcileStreamedContent', () => {
	it('keeps the rendered text while the replay is still catching up (invisible)', () => {
		expect(reconcileStreamedContent('Hello world', 'Hello ')).toBe('Hello world')
	})

	it('adopts the replay once it reaches past the rendered text (appends the tail)', () => {
		expect(reconcileStreamedContent('Hello wo', 'Hello world')).toBe('Hello world')
	})

	it('replaces the rendered text only when the replay diverges (incorrect)', () => {
		expect(reconcileStreamedContent('Hello XYZ', 'Hello world')).toBe('Hello world')
	})

	it('is a no-op when the replay matches exactly', () => {
		expect(reconcileStreamedContent('Hello world', 'Hello world')).toBe('Hello world')
	})
})

function chatDelta(messageId: string, text: string, done = false): ChatStreamDelta {
	return {
		event: 'delta',
		data: {
			run_id: 'run_x',
			agent_id: 'agent_1',
			message_id: messageId,
			parent_id: null,
			delta: {
				chat: { message: { content: [{ type: 'text', text }], tool_calls: null }, done },
			},
		},
	} as unknown as ChatStreamDelta
}

function makeStreamingCtx(content: string): ChatContext {
	const streamingAssistant = {
		runId: 'run_x',
		messageId: 'msg_1',
		content,
		timestamp: new Date(),
		senderAgentId: 'agent_1',
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	return {
		activeRun: 1,
		runAbortController: new AbortController(),
		streamingAssistantParentId: null,
		streamingAssistant,
		appendStreamingText: (text: string) => {
			streamingAssistant.content += text
		},
		flushStreamingText: () => {},
	} as unknown as ChatContext
}

describe('consumeStream reconcile mode (resume)', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
	})

	it('rebuilds resumed content in place without duplicating rendered text', async () => {
		const ctx = makeStreamingCtx('Hello wo')
		await consumeStream(
			asyncFrom([chatDelta('msg_1', 'Hello '), chatDelta('msg_1', 'world')]),
			{ runId: 1, threadId: 'thread_1', parentId: null },
			ctx,
			{ reconcile: true }
		)
		expect(ctx.streamingAssistant?.content).toBe('Hello world')
	})

	it('corrects the rendered text when the replay diverges from it', async () => {
		const ctx = makeStreamingCtx('Hello XYZ')
		await consumeStream(
			asyncFrom([chatDelta('msg_1', 'Hello '), chatDelta('msg_1', 'world')]),
			{ runId: 1, threadId: 'thread_1', parentId: null },
			ctx,
			{ reconcile: true }
		)
		expect(ctx.streamingAssistant?.content).toBe('Hello world')
	})
})

const errorFrame: ChatStreamDelta = {
	event: 'error',
	data: { run_id: 'run_x', message: 'boom' },
} as unknown as ChatStreamDelta

// eslint-disable-next-line require-yield
async function* throwing404Stream(): AsyncGenerator<ChatStreamDelta, void, unknown> {
	throw new StreamHttpError(404)
}

function makeRunCtx(): ChatContext {
	const streamingAssistant = {
		runId: 'run_x',
		messageId: 'msg_1',
		content: 'Hi',
		timestamp: new Date(),
		senderAgentId: 'agent_1',
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
	return {
		activeRun: 5,
		runAbortController: undefined,
		currentLeafId: null,
		viewingStreamingBranch: true,
		streamingAssistantParentId: null,
		streamingLeafId: null,
		citationTargetMessageId: null,
		thread: null,
		messageTree: new Map(),
		citationSources: new Map(),
		rebuildRunBlocks: vi.fn(),
		appendStreamingText: (text: string) => {
			streamingAssistant.content += text
		},
		flushStreamingText: () => {},
		streamingAssistant,
	} as unknown as ChatContext
}

describe('runThreadStream recovery', () => {
	beforeEach(() => {
		activeRunsMocks.forgetRun.mockReset()
		activeRunsMocks.refresh.mockClear()
		activeRunsMocks.getRunsForThread.mockReturnValue([])
		streamMocks.runChatStream.mockReset()
		streamMocks.resumeRunStream.mockReset()
	})

	it('silently resumes the run when the initial stream ends without a terminal event', async () => {
		streamMocks.runChatStream.mockImplementation(() => asyncFrom([]))
		streamMocks.resumeRunStream.mockImplementation(() => asyncFrom([doneFrame]))
		const ctx = makeRunCtx()

		await runThreadStream(
			{ threadId: 'thread_1', agentId: 'agent_1', input: null, runId: 5 },
			ctx
		)

		expect(streamMocks.runChatStream).toHaveBeenCalledTimes(1)
		expect(streamMocks.resumeRunStream).toHaveBeenCalledTimes(1)
		expect(streamMocks.resumeRunStream).toHaveBeenCalledWith(
			expect.objectContaining({ runId: 'run_x' })
		)
	})

	it('does not resume a backend-declared run failure', async () => {
		streamMocks.runChatStream.mockImplementation(() => asyncFrom([errorFrame]))
		const ctx = makeRunCtx()

		await expect(
			runThreadStream(
				{ threadId: 'thread_1', agentId: 'agent_1', input: null, runId: 5 },
				ctx
			)
		).rejects.toBeInstanceOf(RunFailedError)
		expect(streamMocks.resumeRunStream).not.toHaveBeenCalled()
	})

	it('preserves the partial as a clean completion when the resumed run is already finished (404)', async () => {
		streamMocks.runChatStream.mockImplementation(() => asyncFrom([]))
		streamMocks.resumeRunStream.mockImplementation(() => throwing404Stream())
		const ctx = makeRunCtx()

		await runThreadStream(
			{ threadId: 'thread_1', agentId: 'agent_1', input: null, runId: 5 },
			ctx
		)

		const persisted = ctx.messageTree.get('msg_1')
		expect(persisted?.metadata_?.partial).toBe(true)
		expect(activeRunsMocks.forgetRun).toHaveBeenCalledWith('run_x')
	})
})

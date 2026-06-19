import { computeBlockCitations } from '$lib/chat/helpers'
import type { ApiCitation, ApiMessage, StreamingAssistantState } from '$lib/chat/types'
import { describe, expect, it } from 'vitest'

function makeCitation(index: number, sourceType = 'url', sourceId?: string): ApiCitation {
	return {
		index,
		source_type: sourceType as ApiCitation['source_type'],
		source_id: sourceId ?? `https://example.com/${index}`,
		title: `source ${index}`,
	}
}

function makeAssistantMessage(id: string, content: string): ApiMessage {
	return {
		id,
		thread_id: 'thread_1',
		parent_id: null,
		type: 'assistant',
		content: [{ type: 'text', text: content }],
		tool_calls: [],
		sender_agent_id: 'agent_1',
		sender_user_id: null,
		created_at: new Date().toISOString(),
		updated_at: new Date().toISOString(),
	} as ApiMessage
}

function makeStreaming(messageId: string, content: string): StreamingAssistantState {
	return {
		runId: 'run_1',
		messageId,
		content,
		timestamp: new Date(),
		senderAgentId: 'agent_1',
		toolCalls: [],
		isError: false,
		errorMessage: null,
	}
}

describe('computeBlockCitations', () => {
	describe('finalized messages (no streaming)', () => {
		it('returns empty when no messages', () => {
			expect(computeBlockCitations([], null, new Map())).toEqual([])
		})

		it('returns cited sources from the map', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg = makeAssistantMessage('msg_1', 'see [1] and [2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [c1, c2]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c2])
		})

		it('filters to only cited indices', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)
			const msg = makeAssistantMessage('msg_1', 'see [1] and [3]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [c1, c2, c3]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c3])
		})

		it('handles messages with no citations', () => {
			const msg = makeAssistantMessage('msg_1', 'no citations here')
			const items = [{ kind: 'assistant' as const, message: msg }]
			expect(computeBlockCitations(items, null, new Map())).toEqual([])
		})

		it('ignores tool items', () => {
			const c1 = makeCitation(1)
			const msg = makeAssistantMessage('msg_1', 'see [1]')
			const items = [
				{ kind: 'tool' as const, toolCallId: 'tc_1' },
				{ kind: 'assistant' as const, message: msg },
				{ kind: 'streaming_tool' as const, toolCallId: 'tc_2' },
			]
			const map = new Map([['msg_1', [c1]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c1])
		})

		it('combines citations from multiple messages', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg1 = makeAssistantMessage('msg_1', 'see [1]')
			const msg2 = makeAssistantMessage('msg_2', 'see [2]')
			const items = [
				{ kind: 'assistant' as const, message: msg1 },
				{ kind: 'assistant' as const, message: msg2 },
			]
			const map = new Map([
				['msg_1', [c1]],
				['msg_2', [c2]],
			])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c2])
		})

		it('deduplicates citations across messages', () => {
			const c1 = makeCitation(1)
			const msg1 = makeAssistantMessage('msg_1', 'see [1]')
			const msg2 = makeAssistantMessage('msg_2', 'also [1]')
			const items = [
				{ kind: 'assistant' as const, message: msg1 },
				{ kind: 'assistant' as const, message: msg2 },
			]
			const map = new Map([
				['msg_1', [c1]],
				['msg_2', [c1]],
			])

			expect(computeBlockCitations(items, null, map)).toEqual([c1])
		})
	})

	describe('streaming', () => {
		it('returns empty when map has no sources', () => {
			const streaming = makeStreaming('msg_s', 'hello [1]')
			expect(computeBlockCitations([], streaming, new Map())).toEqual([])
		})

		it('returns empty when content has no [n] references', () => {
			const c1 = makeCitation(1)
			const streaming = makeStreaming('msg_s', 'no citations yet')
			const map = new Map([['msg_s', [c1]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([])
		})

		it('returns cited sources when content references them', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const streaming = makeStreaming('msg_s', 'see [1] and [2]')
			const map = new Map([['msg_s', [c1, c2]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([c1, c2])
		})

		it('filters to only actually cited indices', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)
			const streaming = makeStreaming('msg_s', 'only [1] and [3]')
			const map = new Map([['msg_s', [c1, c2, c3]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([c1, c3])
		})

		it('combines finalized and streaming citations', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg = makeAssistantMessage('msg_1', 'earlier [1]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const streaming = makeStreaming('msg_s', 'now [2]')
			const map = new Map([
				['msg_1', [c1]],
				['msg_s', [c1, c2]],
			])

			expect(computeBlockCitations(items, streaming, map)).toEqual([c1, c2])
		})

		it('handles partial [n] at end of stream', () => {
			const c1 = makeCitation(1)
			const streaming = makeStreaming('msg_s', 'see [1] and [')
			const map = new Map([['msg_s', [c1]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([c1])
		})

		it('handles high citation indices', () => {
			const c42 = makeCitation(42)
			const streaming = makeStreaming('msg_s', 'ref [42]')
			const map = new Map([['msg_s', [c42]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([c42])
		})
	})

	describe('footnote-style [^n] citations', () => {
		it('matches [^n] in finalized content', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg = makeAssistantMessage('msg_1', 'see [^1] and [^2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [c1, c2]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c2])
		})

		it('matches [^n] in streaming content', () => {
			const c1 = makeCitation(1)
			const streaming = makeStreaming('msg_s', 'see [^1]')
			const map = new Map([['msg_s', [c1]]])

			expect(computeBlockCitations([], streaming, map)).toEqual([c1])
		})

		it('matches mixed [n] and [^n]', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg = makeAssistantMessage('msg_1', 'see [1] and [^2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [c1, c2]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c2])
		})
	})

	describe('strict message scoping', () => {
		it('ignores citations from messages NOT in the block', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const cOther = makeCitation(3)
			const msg = makeAssistantMessage('msg_1', 'see [1] and [2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			// msg_other is in the map but NOT in the block's responseItems
			const map = new Map([
				['msg_1', [c1, c2]],
				['msg_other', [cOther]],
			])

			const result = computeBlockCitations(items, null, map)
			expect(result).toEqual([c1, c2])
			// cOther (index 3) must NOT be included even though it's in the map
			expect(result.find((c) => c.index === 3)).toBeUndefined()
		})

		it('ignores citations from a different streaming message', () => {
			const c1 = makeCitation(1)
			const cOther = makeCitation(2)
			const streaming = makeStreaming('msg_s', 'see [1]')
			const map = new Map([
				['msg_s', [c1]],
				['msg_unrelated', [cOther]],
			])

			expect(computeBlockCitations([], streaming, map)).toEqual([c1])
		})

		it('only returns sources for messages in THIS block (multi-block scenario)', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const block1Msg = makeAssistantMessage('msg_block1', 'see [1]')
			const block2Msg = makeAssistantMessage('msg_block2', 'see [2]')

			// full map has both blocks' citations
			const map = new Map([
				['msg_block1', [c1]],
				['msg_block2', [c2]],
			])

			// block 1: only msg_block1
			const block1Items = [{ kind: 'assistant' as const, message: block1Msg }]
			expect(computeBlockCitations(block1Items, null, map)).toEqual([c1])

			// block 2: only msg_block2
			const block2Items = [{ kind: 'assistant' as const, message: block2Msg }]
			expect(computeBlockCitations(block2Items, null, map)).toEqual([c2])
		})

		it('does not return uncited sources even if the map has them', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)
			const msg = makeAssistantMessage('msg_1', 'only [2] is cited')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [c1, c2, c3]]])

			expect(computeBlockCitations(items, null, map)).toEqual([c2])
		})
	})

	describe('source type variety', () => {
		it('handles mixed source types (url, note, calendar_event)', () => {
			const cUrl = makeCitation(1, 'url', 'https://example.com')
			const cNote = makeCitation(2, 'note', 'note_abc')
			const cEvent = makeCitation(3, 'calendar_event', 'calev_xyz')
			const msg = makeAssistantMessage('msg_1', 'from [1], [2], and [3]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [cUrl, cNote, cEvent]]])

			const result = computeBlockCitations(items, null, map)
			expect(result).toEqual([cUrl, cNote, cEvent])
			expect(result[0].source_type).toBe('url')
			expect(result[1].source_type).toBe('note')
			expect(result[2].source_type).toBe('calendar_event')
		})

		it('selectively cites from mixed source types', () => {
			const cUrl = makeCitation(1, 'url', 'https://example.com')
			const cNote = makeCitation(2, 'note', 'note_abc')
			const cEvent = makeCitation(3, 'calendar_event', 'calev_xyz')
			const msg = makeAssistantMessage('msg_1', 'only the note [2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const map = new Map([['msg_1', [cUrl, cNote, cEvent]]])

			expect(computeBlockCitations(items, null, map)).toEqual([cNote])
		})
	})

	describe('previous turn citations', () => {
		it('cites sources from a previous message in the same block', () => {
			// multi-iteration agentic block: msg_1 fetched sources, msg_2 cites them
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const msg1 = makeAssistantMessage('msg_1', 'let me look that up')
			const msg2 = makeAssistantMessage('msg_2', 'according to [1] and [2]')
			const items = [
				{ kind: 'assistant' as const, message: msg1 },
				{ kind: 'assistant' as const, message: msg2 },
			]
			// sources are keyed to both messages (run accumulator copies to each)
			const map = new Map([
				['msg_1', [c1, c2]],
				['msg_2', [c1, c2]],
			])

			expect(computeBlockCitations(items, null, map)).toEqual([c1, c2])
		})

		it('cites a subset of previous turn sources', () => {
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)
			const msg1 = makeAssistantMessage('msg_1', 'searching...')
			const msg2 = makeAssistantMessage('msg_2', 'found: only [1] is relevant')
			const items = [
				{ kind: 'assistant' as const, message: msg1 },
				{ kind: 'assistant' as const, message: msg2 },
			]
			const map = new Map([
				['msg_1', [c1, c2, c3]],
				['msg_2', [c1, c2, c3]],
			])

			expect(computeBlockCitations(items, null, map)).toEqual([c1])
		})
	})
})

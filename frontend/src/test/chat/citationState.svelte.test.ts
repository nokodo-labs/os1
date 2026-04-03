/**
 * tests for citation state management: accumulator, SvelteMap, add/flush lifecycle.
 * uses .svelte.test.ts so Svelte 5 runes ($state, SvelteMap) work in the test runtime.
 */
import { computeBlockCitations } from '$lib/chat/helpers'
import type { ApiCitation, ApiMessage, StreamingAssistantState } from '$lib/chat/types'
import { SvelteMap } from 'svelte/reactivity'
import { describe, expect, it } from 'vitest'

function createCitationHarness() {
	const citationSources = new SvelteMap<string, ApiCitation[]>()
	let runCitationAccumulator: ApiCitation[] = []
	let citationTargetMessageId: string | null = null
	let streamingAssistant: StreamingAssistantState | null = $state(null)

	return {
		citationSources,
		get streamingAssistant() {
			return streamingAssistant
		},
		set streamingAssistant(v: StreamingAssistantState | null) {
			streamingAssistant = v
		},
		get citationTargetMessageId() {
			return citationTargetMessageId
		},
		set citationTargetMessageId(v: string | null) {
			citationTargetMessageId = v
		},
		addCitationSources(citations: ApiCitation[]) {
			runCitationAccumulator.push(...citations)
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
		clearThread() {
			citationSources.clear()
			runCitationAccumulator = []
			citationTargetMessageId = null
		},
		incrementActiveRun() {
			runCitationAccumulator = []
			citationTargetMessageId = null
		},
		get accumulatorSize() {
			return runCitationAccumulator.length
		},
	}
}

function makeCitation(index: number, sourceType = 'url'): ApiCitation {
	return {
		index,
		source_type: sourceType as ApiCitation['source_type'],
		source_id: `https://example.com/${index}`,
		title: `source ${index}`,
	}
}

function makeStreamingState(messageId: string, content = ''): StreamingAssistantState {
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

describe('citation state management', () => {
	describe('addCitationSources', () => {
		it('accumulates citations in the run accumulator', () => {
			const h = createCitationHarness()
			h.addCitationSources([makeCitation(1)])
			expect(h.accumulatorSize).toBe(1)
		})

		it('does NOT update map when no target is available', () => {
			const h = createCitationHarness()
			h.addCitationSources([makeCitation(1)])
			expect(h.citationSources.size).toBe(0)
		})

		it('writes to map via streamingAssistant', () => {
			const h = createCitationHarness()
			h.streamingAssistant = makeStreamingState('msg_1')
			h.addCitationSources([makeCitation(1)])
			expect(h.citationSources.get('msg_1')).toEqual([makeCitation(1)])
		})

		it('writes to map via citationTargetMessageId when streaming is null', () => {
			const h = createCitationHarness()
			h.citationTargetMessageId = 'msg_1'
			h.addCitationSources([makeCitation(1)])
			expect(h.citationSources.get('msg_1')).toEqual([makeCitation(1)])
		})

		it('prefers streamingAssistant over citationTargetMessageId', () => {
			const h = createCitationHarness()
			h.citationTargetMessageId = 'msg_old'
			h.streamingAssistant = makeStreamingState('msg_new')
			h.addCitationSources([makeCitation(1)])
			expect(h.citationSources.get('msg_new')).toEqual([makeCitation(1)])
			expect(h.citationSources.has('msg_old')).toBe(false)
		})

		it('accumulates across multiple calls', () => {
			const h = createCitationHarness()
			h.streamingAssistant = makeStreamingState('msg_1')
			h.addCitationSources([makeCitation(1)])
			h.addCitationSources([makeCitation(2)])
			expect(h.citationSources.get('msg_1')).toEqual([makeCitation(1), makeCitation(2)])
		})
	})

	describe('flushCitationsToMessage', () => {
		it('writes accumulator to map for the given messageId', () => {
			const h = createCitationHarness()
			h.addCitationSources([makeCitation(1)])
			h.flushCitationsToMessage('msg_final')
			expect(h.citationSources.get('msg_final')).toEqual([makeCitation(1)])
		})

		it('does nothing when accumulator is empty', () => {
			const h = createCitationHarness()
			h.flushCitationsToMessage('msg_1')
			expect(h.citationSources.size).toBe(0)
		})
	})

	describe('clearThread', () => {
		it('clears everything', () => {
			const h = createCitationHarness()
			h.streamingAssistant = makeStreamingState('msg_1')
			h.addCitationSources([makeCitation(1)])
			h.citationTargetMessageId = 'msg_1'
			h.clearThread()
			expect(h.citationSources.size).toBe(0)
			expect(h.accumulatorSize).toBe(0)
			expect(h.citationTargetMessageId).toBeNull()
		})
	})

	describe('incrementActiveRun', () => {
		it('resets accumulator and target', () => {
			const h = createCitationHarness()
			h.streamingAssistant = makeStreamingState('msg_1')
			h.addCitationSources([makeCitation(1), makeCitation(2)])
			h.citationTargetMessageId = 'msg_1'
			h.incrementActiveRun()
			expect(h.accumulatorSize).toBe(0)
			expect(h.citationTargetMessageId).toBeNull()
		})

		it('prevents old run citations from leaking', () => {
			const h = createCitationHarness()
			h.streamingAssistant = makeStreamingState('msg_run1')
			h.addCitationSources([makeCitation(1), makeCitation(2), makeCitation(3)])
			h.streamingAssistant = null

			h.incrementActiveRun()
			h.streamingAssistant = makeStreamingState('msg_run2')
			h.addCitationSources([makeCitation(1), makeCitation(2)])
			const run2Sources = h.citationSources.get('msg_run2') ?? []
			expect(run2Sources.length).toBe(2)
		})
	})

	describe('full streaming lifecycle: web search with tool call', () => {
		it('produces correct blockCitations through the entire lifecycle', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// tool call iteration has no citations
			h.flushCitationsToMessage('msg_toolcall')
			expect(h.citationSources.size).toBe(0)

			// streaming assistant cycles through pending message
			h.streamingAssistant = makeStreamingState('msg_toolcall')
			h.streamingAssistant = makeStreamingState('pending-next-run1')

			// WS citation events arrive (from filter phase)
			h.addCitationSources([c1, c2])
			expect(h.accumulatorSize).toBe(2)
			expect(h.citationSources.get('pending-next-run1')).toEqual([c1, c2])

			// SSE: new assistant message starts
			h.flushCitationsToMessage('msg_assistant')
			expect(h.citationSources.get('msg_assistant')).toEqual([c1, c2])
			h.streamingAssistant = makeStreamingState('msg_assistant', '')

			// during streaming: nothing is cited yet
			let result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([])

			// content streams with citations
			h.streamingAssistant = makeStreamingState('msg_assistant', 'according to [1]')
			result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([c1])

			// more content
			h.streamingAssistant = makeStreamingState(
				'msg_assistant',
				'according to [1] and also [2]'
			)
			result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([c1, c2])
		})
	})

	describe('page reload: citations from seeded map', () => {
		it('uses seeded map (simulating ingestMessages seeding)', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// simulate ingestMessages seeding citationSources from message.citations
			h.citationSources.set('msg_1', [c1, c2])

			const msg = makeAssistantMessage('msg_1', 'see [1] and [2]')
			const items = [{ kind: 'assistant' as const, message: msg }]
			const result = computeBlockCitations(items, null, h.citationSources)
			expect(result).toEqual([c1, c2])
		})
	})

	describe('regression: WS events arrive after SSE finalization', () => {
		it('late WS citations land on finalized message via citationTargetMessageId', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// SSE streams and finalizes quickly
			h.streamingAssistant = makeStreamingState('msg_1', 'see [1] and [2]')
			h.citationTargetMessageId = 'msg_1'
			h.streamingAssistant = null

			// WS arrives after
			h.addCitationSources([c1, c2])

			// map should have the entry
			expect(h.citationSources.get('msg_1')).toEqual([c1, c2])

			// computeBlockCitations reads from map and filters by content
			const msg = makeAssistantMessage('msg_1', 'see [1] and [2]')
			const result = computeBlockCitations(
				[{ kind: 'assistant', message: msg }],
				null,
				h.citationSources
			)
			expect(result).toEqual([c1, c2])
		})

		it('late WS citations are filtered to cited-only in pill', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)

			h.citationTargetMessageId = 'msg_1'
			h.addCitationSources([c1, c2, c3])

			// content only cites [1] and [3]
			const msg = makeAssistantMessage('msg_1', 'see [1] and [3]')
			const result = computeBlockCitations(
				[{ kind: 'assistant', message: msg }],
				null,
				h.citationSources
			)
			expect(result).toEqual([c1, c3])
		})

		it('citationTargetMessageId resets on new run', () => {
			const h = createCitationHarness()
			h.citationTargetMessageId = 'msg_1'
			h.incrementActiveRun()
			expect(h.citationTargetMessageId).toBeNull()

			// late WS from old run writes nowhere
			h.addCitationSources([makeCitation(1)])
			expect(h.citationSources.size).toBe(0)
		})
	})

	describe('regression: same-run citations (source fetched then cited)', () => {
		it('full lifecycle: tool -> WS events -> response citing sources', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)

			// 1. tool call message streaming + finalization
			h.streamingAssistant = makeStreamingState('msg_toolcall', "I'll search for that")
			h.citationTargetMessageId = 'msg_toolcall'
			// tool calls detected -> pending next
			h.streamingAssistant = makeStreamingState('pending-next-1', '')

			// 2. WS citation events arrive (from filter phase of iteration 2)
			h.addCitationSources([c1, c2, c3])
			expect(h.citationSources.get('pending-next-1')).toEqual([c1, c2, c3])

			// 3. SSE: new assistant message starts
			h.flushCitationsToMessage('msg_response')
			h.streamingAssistant = makeStreamingState('msg_response', '')
			expect(h.citationSources.get('msg_response')).toEqual([c1, c2, c3])

			// 4. MarkdownRenderer reads from map (inline rendering)
			const inlineCitations = h.citationSources.get('msg_response') ?? []
			expect(inlineCitations).toEqual([c1, c2, c3])

			// 5. text with [1] and [3] streams
			h.streamingAssistant = makeStreamingState('msg_response', 'based on [1] and [3]')

			// 6. sources pill shows only cited
			const result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([c1, c3])
		})

		it('WS arrives after SSE finalization but still works', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// tool call finalized
			h.streamingAssistant = makeStreamingState('msg_toolcall', 'searching...')
			h.citationTargetMessageId = 'msg_toolcall'
			h.streamingAssistant = makeStreamingState('pending-next-1', '')

			// SSE: response message comes quickly, finalizes before WS
			h.flushCitationsToMessage('msg_response') // accumulator empty, no-op
			h.streamingAssistant = makeStreamingState('msg_response', 'based on [1] and [2]')
			h.citationTargetMessageId = 'msg_response'
			h.streamingAssistant = null

			// WS events arrive now (late)
			h.addCitationSources([c1, c2])
			expect(h.citationSources.get('msg_response')).toEqual([c1, c2])

			// MarkdownRenderer reads from map -> inline rendering works
			const inlineCitations = h.citationSources.get('msg_response') ?? []
			expect(inlineCitations.length).toBe(2)

			// pill filters to cited only
			const msg = makeAssistantMessage('msg_response', 'based on [1] and [2]')
			const pillResult = computeBlockCitations(
				[{ kind: 'assistant', message: msg }],
				null,
				h.citationSources
			)
			expect(pillResult).toEqual([c1, c2])
		})
	})

	describe('previous turn citations (multi-run)', () => {
		it('run 2 can cite sources fetched in run 1 via seeded map', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// run 1: sources fetched and persisted
			h.streamingAssistant = makeStreamingState('msg_run1', 'found [1] and [2]')
			h.addCitationSources([c1, c2])
			h.citationTargetMessageId = 'msg_run1'
			h.streamingAssistant = null

			// run 1 ends
			h.incrementActiveRun()

			// simulate page reload: ingestMessages seeds the map from msg_run1.citations
			h.citationSources.set('msg_run1', [c1, c2])

			// run 2: user asks follow-up, model cites from run 1's context
			// (WS events for previously fetched sources are re-emitted by the filter)
			const c1Again = makeCitation(1)
			const c2Again = makeCitation(2)
			h.streamingAssistant = makeStreamingState('msg_run2', '')
			h.addCitationSources([c1Again, c2Again])
			h.streamingAssistant = makeStreamingState('msg_run2', 'as we saw [1]')

			// run 2's message should have its OWN copy of citations
			expect(h.citationSources.get('msg_run2')).toEqual([c1Again, c2Again])

			// pill for run 2 block shows only what run 2 cites
			const result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([c1Again])
		})

		it('run 1 citations stay isolated in the map after run 2 starts', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)

			// run 1 seeded
			h.citationSources.set('msg_run1', [c1, c2])

			// run 2 has its own sources
			const c3 = makeCitation(3)
			h.streamingAssistant = makeStreamingState('msg_run2', '')
			h.addCitationSources([c3])

			// run 1's entry is untouched
			expect(h.citationSources.get('msg_run1')).toEqual([c1, c2])
			// run 2 has only its own
			expect(h.citationSources.get('msg_run2')).toEqual([c3])
		})
	})

	describe('cross-block isolation', () => {
		it('computeBlockCitations scopes to only the provided responseItems', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)

			// two blocks exist in the map
			h.citationSources.set('msg_block1', [c1, c2])
			h.citationSources.set('msg_block2', [c3])

			// block 1 rendering
			const block1Msg = makeAssistantMessage('msg_block1', 'see [1]')
			const block1Result = computeBlockCitations(
				[{ kind: 'assistant', message: block1Msg }],
				null,
				h.citationSources
			)
			expect(block1Result).toEqual([c1])
			expect(block1Result.find((c) => c.index === 3)).toBeUndefined()

			// block 2 rendering
			const block2Msg = makeAssistantMessage('msg_block2', 'see [3]')
			const block2Result = computeBlockCitations(
				[{ kind: 'assistant', message: block2Msg }],
				null,
				h.citationSources
			)
			expect(block2Result).toEqual([c3])
			expect(block2Result.find((c) => c.index === 1)).toBeUndefined()
		})
	})

	describe('source type variety', () => {
		it('handles url, note, and tool_result source types', () => {
			const h = createCitationHarness()
			const cUrl = makeCitation(1, 'url')
			const cNote = makeCitation(2, 'note')
			const cTool = makeCitation(3, 'tool_result')

			h.streamingAssistant = makeStreamingState('msg_1', '')
			h.addCitationSources([cUrl, cNote, cTool])
			h.streamingAssistant = makeStreamingState('msg_1', 'see [1], [2], [3]')

			const result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toHaveLength(3)
			expect(result.map((c) => c.source_type)).toEqual(['url', 'note', 'tool_result'])
		})
	})

	describe('multi-iteration agentic loop', () => {
		it('accumulates citations across multiple tool call iterations', () => {
			const h = createCitationHarness()

			// iteration 1: first tool call, 2 sources
			h.streamingAssistant = makeStreamingState('msg_tc1', 'searching...')
			h.citationTargetMessageId = 'msg_tc1'
			h.streamingAssistant = makeStreamingState('pending-1', '')
			h.addCitationSources([makeCitation(1), makeCitation(2)])

			// iteration 2: second tool call, 1 more source
			h.flushCitationsToMessage('msg_tc2')
			h.streamingAssistant = makeStreamingState('msg_tc2', 'digging deeper...')
			h.citationTargetMessageId = 'msg_tc2'
			h.streamingAssistant = makeStreamingState('pending-2', '')
			h.addCitationSources([makeCitation(3)])

			// iteration 3: final response cites all three
			h.flushCitationsToMessage('msg_final')
			h.streamingAssistant = makeStreamingState('msg_final', 'based on [1], [2] and [3]')

			const result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toHaveLength(3)
		})

		it('final response cites only a subset of accumulated sources', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)
			const c4 = makeCitation(4)

			// all 4 sources accumulated from tool calls
			h.streamingAssistant = makeStreamingState('pending', '')
			h.addCitationSources([c1, c2, c3, c4])

			// final response only cites [1] and [4]
			h.flushCitationsToMessage('msg_final')
			h.streamingAssistant = makeStreamingState('msg_final', 'comparing [1] with [4]')

			const result = computeBlockCitations([], h.streamingAssistant, h.citationSources)
			expect(result).toEqual([c1, c4])
			expect(result.find((c) => c.index === 2)).toBeUndefined()
			expect(result.find((c) => c.index === 3)).toBeUndefined()
		})
	})

	describe('page reload: per-message isolation', () => {
		it('seeded map correctly scopes citations per message', () => {
			const h = createCitationHarness()
			const c1 = makeCitation(1)
			const c2 = makeCitation(2)
			const c3 = makeCitation(3)

			// simulate ingestMessages seeding from different messages
			h.citationSources.set('msg_a', [c1, c2])
			h.citationSources.set('msg_b', [c3])

			// block A: only msg_a
			const msgA = makeAssistantMessage('msg_a', 'see [1] and [2]')
			const resultA = computeBlockCitations(
				[{ kind: 'assistant', message: msgA }],
				null,
				h.citationSources
			)
			expect(resultA).toEqual([c1, c2])

			// block B: only msg_b
			const msgB = makeAssistantMessage('msg_b', 'and also [3]')
			const resultB = computeBlockCitations(
				[{ kind: 'assistant', message: msgB }],
				null,
				h.citationSources
			)
			expect(resultB).toEqual([c3])
			expect(resultB.find((c) => c.index === 1)).toBeUndefined()
		})

		it('message with no citations in map returns empty', () => {
			const h = createCitationHarness()
			h.citationSources.set('msg_other', [makeCitation(1)])

			const msg = makeAssistantMessage('msg_no_citations', 'no sources [1]')
			const result = computeBlockCitations(
				[{ kind: 'assistant', message: msg }],
				null,
				h.citationSources
			)
			// msg_no_citations has no entry in the map, so nothing to return
			expect(result).toEqual([])
		})
	})
})

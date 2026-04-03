/**
 * component-level reactivity tests for the citation pill rendering pattern.
 */
import type { ApiCitation, StreamingAssistantState } from '$lib/chat/types'
import { render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { SvelteMap } from 'svelte/reactivity'
import { describe, expect, it } from 'vitest'
import CitationReactivityFixture from './CitationReactivityFixture.svelte'

function makeCitation(index: number): ApiCitation {
	return {
		index,
		source_type: 'url',
		source_id: `https://example.com/${index}`,
		title: `source ${index}`,
	}
}

describe('citation pill reactivity', () => {
	it('shows pill when sources and content both have citations', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()
		sources.set('msg_1', [makeCitation(1), makeCitation(2)])

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: 'hello [1] world',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()

		expect(screen.getByTestId('debug-block-citations').textContent).toBe('1')
		expect(screen.getByTestId('sources-pill')).toBeTruthy()
	})

	it('does not show pill when content has no [n] references', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()
		sources.set('msg_1', [makeCitation(1)])

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: 'no citations yet',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()

		expect(screen.getByTestId('debug-block-citations').textContent).toBe('0')
		expect(screen.queryByTestId('sources-pill')).toBeNull()
	})

	it('pill appears reactively when content updates to include [n]', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()
		sources.set('msg_1', [makeCitation(1), makeCitation(2)])

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: '',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()
		expect(screen.queryByTestId('sources-pill')).toBeNull()

		streaming.content = 'based on the results [1]'
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 1')
	})

	it('pill updates as more citations are referenced', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()
		sources.set('msg_1', [makeCitation(1), makeCitation(2), makeCitation(3)])

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: '',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()

		streaming.content = 'see [1]'
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 1')

		streaming.content = 'see [1] and also [2]'
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 2')

		streaming.content = 'see [1] and also [2] plus [3]'
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 3')
	})

	it('pill appears when citationSources map is updated after render', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: 'see [1]',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()
		expect(screen.queryByTestId('sources-pill')).toBeNull()

		sources.set('msg_1', [makeCitation(1)])
		await tick()
		expect(screen.getByTestId('sources-pill')).toBeTruthy()
	})

	it('regression: same-run citations arrive after content with [n] has streamed', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()

		// 1. streaming starts with empty content, no citations yet
		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_response',
			content: '',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()

		// 2. content streams in with [1] marker - but no citations in map yet
		streaming.content = 'based on [1] the answer is clear'
		await tick()
		expect(screen.getByTestId('debug-stream-sources').textContent).toBe('0')
		expect(screen.queryByTestId('sources-pill')).toBeNull()

		// 3. WS citation event arrives late (the race condition)
		sources.set('msg_response', [makeCitation(1)])
		await tick()

		// 4. pill should now appear reactively
		expect(screen.getByTestId('debug-stream-sources').textContent).toBe('1')
		expect(screen.getByTestId('sources-pill')).toBeTruthy()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 1')
	})

	it('regression: same-run multiple citations arrive incrementally', async () => {
		const sources = new SvelteMap<string, ApiCitation[]>()

		const streaming: StreamingAssistantState = $state({
			runId: 'run_1',
			messageId: 'msg_1',
			content: 'see [1] and [2]',
			timestamp: new Date(),
			senderAgentId: 'agent_1',
			toolCalls: [],
			isError: false,
			errorMessage: null,
		})

		render(CitationReactivityFixture, {
			props: { citationSources: sources, streamingAssistant: streaming },
		})
		await tick()
		expect(screen.queryByTestId('sources-pill')).toBeNull()

		// first batch arrives
		sources.set('msg_1', [makeCitation(1)])
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 1')

		// second batch arrives (accumulator grows)
		sources.set('msg_1', [makeCitation(1), makeCitation(2)])
		await tick()
		expect(screen.getByTestId('sources-pill').textContent).toBe('sources: 2')
	})
})

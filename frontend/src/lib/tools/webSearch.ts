/** parses web search tool progress and results for rich chat rendering. */

import { isRecord, readFiniteNumber, readNonEmptyString, readRecordArray } from '$lib/utils/records'
import { safeHostname } from '$lib/utils/url'
import type { ToolEvent, ToolExecution } from './types'

export interface WebSearchSourceView {
	url: string
	title: string | null
	snippet?: string | null
	domain: string
}

export interface WebSearchProgressItem {
	id: string
	stage: string | null
	message: string
	query: string | null
	resultCount: number | null
	sourceCount: number | null
	agent: string | null
	engine: string | null
}

/** returns the unique search queries represented by a web search execution. */
export function getWebSearchQueries(execution: ToolExecution): string[] {
	const queries = new Set<string>()
	const addQuery = (query: string | null) => {
		if (query) queries.add(query)
	}

	for (const event of execution.events) {
		const rawPayload = event.data.payload
		const richPayload = readWebSearchPayload(rawPayload)
		if (richPayload) {
			addQuery(readQueryText(richPayload.query))
			for (const search of readRecordArray(richPayload.searches)) {
				addQuery(readQueryText(search.query))
			}
		}

		if (isRecord(rawPayload) && Array.isArray(rawPayload.queries)) {
			for (const query of rawPayload.queries) addQuery(readNonEmptyString(query))
		}
	}

	addQuery(readNonEmptyString(execution.toolCall.arguments.query))
	return [...queries]
}

/** returns source cards extracted from web search events or result output. */
export function getWebSearchSources(execution: ToolExecution): WebSearchSourceView[] {
	const sources = new Map<string, WebSearchSourceView>()
	const addSources = (items: WebSearchSourceView[]) => {
		for (const item of items) sources.set(item.url, item)
	}

	for (const event of execution.events) {
		addSources(readWebSearchSources(event.data.payload))
	}

	if (sources.size > 0) return [...sources.values()]

	if (execution.result && !execution.result.isError) {
		const outputSources = readWebSearchOutputSources(execution.result.output)
		if (outputSources.length > 0) return outputSources
	}

	if (execution.result && !execution.result.isError) {
		return parseWebSearchSourcesFromText(execution.result.output)
	}
	return []
}

/** returns normalized progress items for the web search body component. */
export function getWebSearchProgressItems(execution: ToolExecution): WebSearchProgressItem[] {
	return execution.events
		.map((event) => {
			const richPayload = readWebSearchPayload(event.data.payload)
			if (!richPayload) {
				const message = event.data.message ?? event.data.description
				if (!message) return null
				return {
					id: event.id,
					stage: null,
					message,
					query: null,
					resultCount: null,
					sourceCount: null,
					agent: null,
					engine: null,
				}
			}

			const searches = readRecordArray(richPayload.searches)
			const firstSearch = searches[0]
			const resources = isRecord(richPayload.resources) ? richPayload.resources : null
			const resourceSources = resources ? readSourceItems(resources.sources) : []
			const stage = readNonEmptyString(richPayload.stage)
			const message =
				readNonEmptyString(richPayload.message) ?? event.data.message ?? stage ?? 'update'

			return {
				id: event.id,
				stage,
				message,
				query: readQueryText(firstSearch?.query) ?? readQueryText(richPayload.query),
				resultCount: readFiniteNumber(firstSearch?.result_count),
				sourceCount:
					resourceSources.length > 0
						? resourceSources.length
						: readFiniteNumber(resources?.count),
				agent: readNamedValue(richPayload.agent),
				engine: readNamedValue(richPayload.engine),
			}
		})
		.filter((item): item is WebSearchProgressItem => item !== null)
}

/** returns a short progress message from a rich web search event. */
export function formatWebSearchProgressLine(event: ToolEvent): string | null {
	const richPayload = readWebSearchPayload(event.data.payload)
	if (!richPayload) return null
	return readNonEmptyString(richPayload.message)
}

/** returns the best available source count for a completed web search execution. */
export function countWebSearchSources(execution: ToolExecution): number | null {
	const richSources = getWebSearchSources(execution)
	if (richSources.length > 0) return richSources.length

	let latestCount: number | null = null
	for (const event of execution.events) {
		const richPayload = readWebSearchPayload(event.data.payload)
		const resources =
			richPayload && isRecord(richPayload.resources) ? richPayload.resources : null
		latestCount = readFiniteNumber(resources?.count) ?? latestCount
	}
	return latestCount
}

/** reads a name field from either a string or nested object. */
function readNamedValue(value: unknown): string | null {
	if (typeof value === 'string') return readNonEmptyString(value)
	if (isRecord(value)) return readNonEmptyString(value.name)
	return null
}

/** reads query text from either a string or nested object. */
function readQueryText(value: unknown): string | null {
	if (typeof value === 'string') return readNonEmptyString(value)
	if (isRecord(value)) return readNonEmptyString(value.text)
	return null
}

/** unwraps the rich web search payload shape emitted by tool progress events. */
function readWebSearchPayload(payload: unknown): Record<string, unknown> | null {
	if (!isRecord(payload)) return null
	const nested = payload.web_search
	if (isRecord(nested)) return nested
	return payload.kind === 'agentic_web_search' ? payload : null
}

/** extracts source items from the supported web search payload variants. */
function readWebSearchSources(payload: unknown): WebSearchSourceView[] {
	const richPayload = readWebSearchPayload(payload)
	if (richPayload) {
		const resources = isRecord(richPayload.resources) ? richPayload.resources : null
		const resourceSources = resources ? readSourceItems(resources.sources) : []
		if (resourceSources.length > 0) return resourceSources

		for (const search of readRecordArray(richPayload.searches)) {
			const searchSources = readSourceItems(search.sources)
			if (searchSources.length > 0) return searchSources
		}
	}

	if (isRecord(payload)) return readSourceItems(payload.sources)
	return []
}

/** extracts source items from json tool output. */
function readWebSearchOutputSources(output: string): WebSearchSourceView[] {
	try {
		const parsed: unknown = JSON.parse(output)
		if (!isRecord(parsed)) return []
		const resultSources = readSourceItems(parsed.results)
		if (resultSources.length > 0) return resultSources
		return []
	} catch {
		return []
	}
}

/** normalizes raw source objects into deduped source views. */
function readSourceItems(value: unknown): WebSearchSourceView[] {
	if (!Array.isArray(value)) return []
	const sources: WebSearchSourceView[] = []
	const seenUrls = new Set<string>()
	for (const item of value) {
		if (!isRecord(item)) continue
		const url = readNonEmptyString(item.url)
		if (!url || seenUrls.has(url)) continue
		seenUrls.add(url)
		sources.push({
			url,
			title: readNonEmptyString(item.title),
			snippet: readNonEmptyString(item.snippet),
			domain: safeHostname(url) ?? url,
		})
	}
	return sources
}

/** parses plain-text numbered source lists produced by older web search results. */
function parseWebSearchSourcesFromText(text: string): WebSearchSourceView[] {
	const results: WebSearchSourceView[] = []
	const lines = text.split('\n')
	for (const line of lines) {
		const match = line.match(/^\d+\.\s*(.+?)\s*-\s*(https?:\/\/\S+)/)
		if (!match) continue
		const title = match[1].trim()
		const url = match[2].trim()
		results.push({
			url,
			title: title || null,
			domain: safeHostname(url) ?? url,
		})
	}
	return results
}

import type { ToolEvent, ToolExecution } from './index'

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
				resultCount: readNumber(firstSearch?.result_count),
				sourceCount:
					resourceSources.length > 0
						? resourceSources.length
						: readNumber(resources?.count),
				agent: readNamedValue(richPayload.agent),
				engine: readNamedValue(richPayload.engine),
			}
		})
		.filter((item): item is WebSearchProgressItem => item !== null)
}

export function formatWebSearchProgressLine(event: ToolEvent): string | null {
	const richPayload = readWebSearchPayload(event.data.payload)
	if (!richPayload) return null
	return readNonEmptyString(richPayload.message)
}

export function countWebSearchSources(execution: ToolExecution): number | null {
	const richSources = getWebSearchSources(execution)
	if (richSources.length > 0) return richSources.length

	let latestCount: number | null = null
	for (const event of execution.events) {
		const richPayload = readWebSearchPayload(event.data.payload)
		const resources =
			richPayload && isRecord(richPayload.resources) ? richPayload.resources : null
		latestCount = readNumber(resources?.count) ?? latestCount
	}
	return latestCount
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readNonEmptyString(value: unknown): string | null {
	if (typeof value !== 'string') return null
	const trimmed = value.trim()
	return trimmed.length > 0 ? trimmed : null
}

function readNumber(value: unknown): number | null {
	return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function readNamedValue(value: unknown): string | null {
	if (typeof value === 'string') return readNonEmptyString(value)
	if (isRecord(value)) return readNonEmptyString(value.name)
	return null
}

function readQueryText(value: unknown): string | null {
	if (typeof value === 'string') return readNonEmptyString(value)
	if (isRecord(value)) return readNonEmptyString(value.text)
	return null
}

function readRecordArray(value: unknown): Record<string, unknown>[] {
	if (!Array.isArray(value)) return []
	return value.filter((item): item is Record<string, unknown> => isRecord(item))
}

function readWebSearchPayload(payload: unknown): Record<string, unknown> | null {
	if (!isRecord(payload)) return null
	const nested = payload.web_search
	if (isRecord(nested)) return nested
	return payload.kind === 'agentic_web_search' ? payload : null
}

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

function safeHostname(url: string): string | null {
	try {
		return new URL(url).hostname.replace(/^www\./, '')
	} catch {
		return null
	}
}

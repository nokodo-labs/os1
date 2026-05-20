/** summarizes media generation tool executions. */

import { readNumberField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes image generation and image edit executions. */
export function summarizeGenerateImage(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not create image' }
	if (isActive) return { title: 'creating image' }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count') ?? 1
	const action = typeof args.file_id === 'string' ? 'edited' : 'created'
	return { title: `${action} ${count} ${count === 1 ? 'image' : 'images'}` }
}

/** summarizes video generation executions. */
export function summarizeGenerateVideo(execution: ToolExecution): ToolSummary {
	const { isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not create video' }
	if (isActive) return { title: 'creating video' }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count') ?? 1
	return { title: `created ${count} ${count === 1 ? 'video' : 'videos'}` }
}

/** summarizes audio generation executions. */
export function summarizeGenerateAudio(execution: ToolExecution): ToolSummary {
	const { isActive, isFailed } = getToolSummaryState(execution)
	if (isFailed) return { title: 'could not create audio' }
	if (isActive) return { title: 'creating audio' }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count') ?? 1
	return { title: `created ${count} audio ${count === 1 ? 'clip' : 'clips'}` }
}

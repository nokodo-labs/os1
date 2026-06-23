/** summarizes project read and search tool executions. */

import { projects } from '$lib/stores/projects.svelte'
import { readNonEmptyString, readNumberField, readStringField } from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes project search, list, and direct read executions. */
export function summarizeProjectGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const projectId = readNonEmptyString(args.project_id)
	if (isFailed) return { title: 'could not check projects' }

	if (projectId) {
		const label = projects.getById(projectId)?.name
		if (isActive) return { title: label ? `checking ${label}` : 'checking project' }
		const output = parseToolOutput(execution)
		const name = readStringField(output, 'name') ?? label
		return {
			title: name ? `checked ${name}` : 'checked project',
			resourceId: projectId,
			resourceType: 'project',
		}
	}

	const query = readNonEmptyString(args.query)
	if (isActive) return { title: 'searching projects', subtitle: query ?? undefined }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(count, 'project', 'projects', 'no projects found'),
			subtitle: query ?? undefined,
		}
	}
	return { title: 'searched projects', subtitle: query ?? undefined }
}

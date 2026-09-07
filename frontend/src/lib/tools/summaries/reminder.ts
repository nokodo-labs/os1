/** summarizes reminder and reminder-list tool executions. */

import {
	readNonEmptyString,
	readNumberField,
	readRecordField,
	readStringField,
} from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, listedTitle, parseToolOutput } from './summaryState'

/** summarizes reminder fetch, list fetch, list, and search executions. */
export function summarizeReminderGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const reminderId = readNonEmptyString(args.reminder_id)
	const listId = readNonEmptyString(args.list_id)

	if (isFailed) return { title: 'could not check reminders' }
	if (reminderId) return summarizeReminderRead(execution, reminderId, isActive)
	if (listId) return summarizeReminderListRead(execution, listId, isActive)
	return summarizeReminderSearchOrList(execution, isActive)
}

/** summarizes reminder create, update, complete, and delete executions. */
export function summarizeReminderWrite(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const reminderTitle = readNonEmptyString(args.title)
	const reminderId = readNonEmptyString(args.reminder_id)
	const isUpdate = reminderId !== null

	if (isFailed) return { title: 'could not set reminder' }
	if (isActive) {
		const verb = isUpdate ? 'updating' : 'creating'
		return { title: reminderTitle ? `${verb} ${reminderTitle}` : `${verb} reminder` }
	}

	const output = parseToolOutput(execution)
	const resultId = readStringField(output, 'id')
	const doneVerb = isUpdate ? 'updated' : 'created'
	return {
		title: reminderTitle ? `${doneVerb} ${reminderTitle}` : `${doneVerb} reminder`,
		resourceId: resultId ?? reminderId ?? undefined,
		resourceType: 'reminder',
	}
}

/** summarizes a direct reminder read execution. */
function summarizeReminderRead(
	execution: ToolExecution,
	reminderId: string,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: 'checking reminder' }
	const output = parseToolOutput(execution)
	const reminder = readRecordField(output, 'reminder')
	const title = readStringField(reminder, 'title')
	return {
		title: title ? `checked ${title}` : 'checked reminder',
		resourceId: reminderId,
		resourceType: 'reminder',
	}
}

/** summarizes a direct reminder-list read execution. */
function summarizeReminderListRead(
	execution: ToolExecution,
	listId: string,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: 'checking reminder list' }
	const output = parseToolOutput(execution)
	const list = readRecordField(output, 'list')
	const name = readStringField(list, 'name')
	return {
		title: name ? `checked ${name}` : 'checked reminder list',
		resourceId: listId,
		resourceType: 'reminder_list',
	}
}

/** summarizes reminder search output or reminder-list listing output. */
function summarizeReminderSearchOrList(execution: ToolExecution, isActive: boolean): ToolSummary {
	const query = readNonEmptyString(execution.toolCall.arguments.query)
	if (!query) return summarizeReminderListListing(execution, isActive)
	if (isActive) return { title: 'searching reminders', subtitle: query }

	const output = parseToolOutput(execution)
	const listCount = readNumberField(output, 'list_count')
	const reminderCount = readNumberField(output, 'reminder_count')
	if (listCount !== null || reminderCount !== null) {
		const total = (listCount ?? 0) + (reminderCount ?? 0)
		return {
			title: countTitle(total, 'reminder result', 'reminder results', 'no reminders found'),
			subtitle: query,
		}
	}
	return { title: 'searched reminders', subtitle: query }
}

/** summarizes a plain reminder-list listing, which fetched rather than searched. */
function summarizeReminderListListing(execution: ToolExecution, isActive: boolean): ToolSummary {
	if (isActive) return { title: 'listing reminder lists' }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return { title: listedTitle(count, 'reminder list', 'reminder lists', 'no reminder lists') }
	}
	return { title: 'listed reminder lists' }
}

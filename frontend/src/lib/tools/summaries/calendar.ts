/** summarizes calendar event read, search, upcoming, and write tool executions. */

import {
	readNonEmptyString,
	readNumberField,
	readRecordField,
	readStringField,
} from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes calendar event fetch, search, and upcoming executions. */
export function summarizeCalendarEventGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const eventId = readNonEmptyString(args.calendar_event_id)
	const query = readNonEmptyString(args.query)

	if (isFailed) return { title: 'could not check calendar' }
	if (eventId) return summarizeCalendarEventRead(execution, eventId, isActive)
	if (query) return summarizeCalendarEventSearch(execution, query, isActive)
	if (isActive) return { title: 'checking what is coming up' }

	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(count, 'scheduled item', 'scheduled items', 'nothing coming up'),
		}
	}
	return { title: 'checked calendar' }
}

/** summarizes calendar event create, update, and delete executions. */
export function summarizeCalendarEventWrite(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const eventTitle = readNonEmptyString(args.title)
	const eventId = readNonEmptyString(args.calendar_event_id)
	const isDelete = args.delete === true

	if (isFailed) return { title: 'could not edit calendar' }
	if (isActive) {
		if (isDelete) return { title: 'deleting calendar event' }
		return { title: eventTitle ? `saving ${eventTitle}` : 'saving calendar event' }
	}

	const output = parseToolOutput(execution)
	const event = readRecordField(output, 'event')
	const title = readStringField(event, 'title') ?? eventTitle
	const outputEventId = readStringField(event, 'id') ?? eventId
	if (isDelete) {
		return {
			title: 'deleted calendar event',
			resourceId: outputEventId ?? undefined,
			resourceType: 'calendar_event',
		}
	}

	const isUpdate = eventId !== null
	return {
		title: title
			? `${isUpdate ? 'updated' : 'created'} ${title}`
			: `${isUpdate ? 'updated' : 'created'} calendar event`,
		resourceId: outputEventId ?? undefined,
		resourceType: 'calendar_event',
	}
}

/** summarizes a direct calendar event read execution. */
function summarizeCalendarEventRead(
	execution: ToolExecution,
	eventId: string,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: 'reading calendar event' }
	const output = parseToolOutput(execution)
	const event = readRecordField(output, 'event')
	const title = readStringField(event, 'title')
	return {
		title: title ? `read ${title}` : 'read calendar event',
		resourceId: eventId,
		resourceType: 'calendar_event',
	}
}

/** summarizes a calendar event search execution. */
function summarizeCalendarEventSearch(
	execution: ToolExecution,
	query: string,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: 'searching calendar', subtitle: query }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return {
			title: countTitle(
				count,
				'calendar event',
				'calendar events',
				'no calendar events found'
			),
			subtitle: query,
		}
	}
	return { title: 'searched calendar', subtitle: query }
}

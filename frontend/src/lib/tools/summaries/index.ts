/** dispatches tool executions to per-tool summary handlers. */

import { formatToolEventLine } from '../display'
import { getToolDisplayName } from '../registry'
import type { ToolExecution, ToolSummary } from '../types'
import { summarizeCalendarEventGet, summarizeCalendarEventWrite } from './calendar'
import { summarizeChatGet } from './chat'
import { summarizeCodeInterpreter } from './code'
import { summarizeFileEdit, summarizeFileGet } from './file'
import { summarizeGenerateAudio, summarizeGenerateImage, summarizeGenerateVideo } from './media'
import { summarizeMemoryCreate, summarizeMemoryRecall } from './memory'
import { summarizeNoteGet, summarizeNoteWrite } from './note'
import { summarizeProjectGet } from './project'
import { summarizeReminderGet, summarizeReminderWrite } from './reminder'
import { summarizeResourceSearch } from './resourceSearch'
import { getThinkElapsed, getThinkTitle, summarizeThink } from './think'
import { summarizeAgenticWebSearch, summarizeFetchUrl } from './web'
import { summarizeRevealAttachment, summarizeSendNotification } from './notification'

type ToolSummaryHandler = (execution: ToolExecution) => ToolSummary

const summaryHandlers = new Map<string, ToolSummaryHandler>([
	['resource_search', summarizeResourceSearch],
	['chat_get', summarizeChatGet],
	['think', summarizeThink],
	['agentic_web_search', summarizeAgenticWebSearch],
	['fetch_url', summarizeFetchUrl],
	['memory_recall', summarizeMemoryRecall],
	['memory_create', summarizeMemoryCreate],
	['note_get', summarizeNoteGet],
	['note_write', summarizeNoteWrite],
	['project_get', summarizeProjectGet],
	['calendar_event_get', summarizeCalendarEventGet],
	['calendar_event_write', summarizeCalendarEventWrite],
	['reminder_get', summarizeReminderGet],
	['reminder_write', summarizeReminderWrite],
	['file_get', summarizeFileGet],
	['file_edit', summarizeFileEdit],
	['generate_image', summarizeGenerateImage],
	['generate_video', summarizeGenerateVideo],
	['generate_audio', summarizeGenerateAudio],
	['code_interpreter', summarizeCodeInterpreter],
	['send_notification', summarizeSendNotification],
	['reveal_attachment', summarizeRevealAttachment],
])

export { getThinkElapsed, getThinkTitle }

/** returns the compact title/subtitle/resource summary for a tool execution. */
export function getToolSummary(execution: ToolExecution): ToolSummary {
	const handler = summaryHandlers.get(execution.toolCall.name)
	if (handler) return handler(execution)
	return summarizeGenericTool(execution)
}

/** builds a fallback summary for tools without a dedicated handler. */
function summarizeGenericTool(execution: ToolExecution): ToolSummary {
	const displayName = getToolDisplayName(execution.toolCall.name)
	if (execution.lastMessage) return { title: displayName, subtitle: execution.lastMessage }

	const latestEvent = execution.events.at(-1)
	if (latestEvent) {
		return { title: displayName, subtitle: formatToolEventLine(latestEvent) }
	}
	return { title: displayName }
}

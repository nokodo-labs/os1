/** summarizes chat read, list, and search tool executions. */

import {
	readNonEmptyString,
	readNumberField,
	readRecordField,
	readStringField,
} from '$lib/utils/records'
import type { ToolExecution, ToolSummary } from '../types'
import { countTitle, getToolSummaryState, parseToolOutput } from './summaryState'

/** summarizes chat search, list, and direct read executions. */
export function summarizeChatGet(execution: ToolExecution): ToolSummary {
	const { args, isActive, isFailed } = getToolSummaryState(execution)
	const chatId = readNonEmptyString(args.chat_id)
	const messageId = readNonEmptyString(args.message_id)
	const query = readNonEmptyString(args.query)

	if (isFailed) return { title: 'could not check chats' }
	if (query) return summarizeChatSearch(execution, query, isActive)
	if (chatId || messageId) return summarizeChatRead(execution, chatId, messageId, isActive)
	if (isActive) return { title: 'listing chats' }

	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) return { title: countTitle(count, 'chat', 'chats', 'no chats found') }
	return { title: 'listed chats' }
}

/** summarizes a chat search execution. */
function summarizeChatSearch(
	execution: ToolExecution,
	query: string,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: 'searching chats', subtitle: query }
	const output = parseToolOutput(execution)
	const count = readNumberField(output, 'count')
	if (count !== null) {
		return { title: countTitle(count, 'chat', 'chats', 'no chats found'), subtitle: query }
	}
	return { title: 'searched chats', subtitle: query }
}

/** summarizes a direct chat or chat message read execution. */
function summarizeChatRead(
	execution: ToolExecution,
	chatId: string | null,
	messageId: string | null,
	isActive: boolean
): ToolSummary {
	if (isActive) return { title: messageId ? 'finding chat message' : 'reading chat' }
	const output = parseToolOutput(execution)
	const chat = readRecordField(output, 'chat')
	const title = readStringField(chat, 'title')
	const outputChatId = readStringField(chat, 'chat_id')
	return {
		title: title ? `read ${title}` : 'read chat',
		resourceId: outputChatId ?? chatId ?? undefined,
		resourceType: 'chat',
	}
}

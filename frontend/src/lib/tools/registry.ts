/** registry of native tool display metadata used by the chat UI. */

export interface NativeToolDefinition<TArgs = Record<string, unknown>> {
	displayName: string
	icon?: string
	inline?: boolean
	parseArgs?: (args: Record<string, unknown>) => TArgs | null
}

const nativeTools = new Map<string, NativeToolDefinition>([
	['resource_search', { displayName: 'search resources', icon: 'search', inline: true }],
	['chat_get', { displayName: 'check chats', icon: 'chat', inline: true }],
	['think', { displayName: 'thinking', icon: 'brain', inline: true }],
	['agentic_web_search', { displayName: 'web search', icon: 'globe', inline: true }],
	['fetch_url', { displayName: 'browse page', icon: 'globe', inline: true }],
	['memory_recall', { displayName: 'recall memories', icon: 'brain', inline: true }],
	['memory_create', { displayName: 'save memory', icon: 'brain', inline: true }],
	['note_get', { displayName: 'read note', icon: 'note', inline: true }],
	['note_write', { displayName: 'write note', icon: 'note', inline: true }],
	['project_get', { displayName: 'check projects', icon: 'folder', inline: true }],
	['calendar_event_get', { displayName: 'check calendar', icon: 'calendar', inline: true }],
	['calendar_event_write', { displayName: 'edit calendar', icon: 'calendar', inline: true }],
	['reminder_get', { displayName: 'check reminders', icon: 'bell', inline: true }],
	['reminder_write', { displayName: 'set reminder', icon: 'bell', inline: true }],
	['file_get', { displayName: 'read file', icon: 'document', inline: true }],
	['file_edit', { displayName: 'edit file', icon: 'pencil', inline: true }],
	['generate_image', { displayName: 'create image', icon: 'photo', inline: true }],
	['generate_video', { displayName: 'create video', icon: 'film', inline: true }],
	['generate_audio', { displayName: 'create audio', icon: 'headphone', inline: true }],
	['code_interpreter', { displayName: 'run code', icon: 'terminal', inline: true }],
	[
		'send_notification',
		{
			displayName: 'send notification',
			icon: 'bell',
			inline: true,
			parseArgs: (args: Record<string, unknown>) => {
				const title = typeof args.title === 'string' ? args.title : null
				const body = typeof args.body === 'string' ? args.body : null
				const userId = typeof args.user_id === 'string' ? args.user_id : null
				if (!title || !body) return null
				return userId ? { title, body, user_id: userId } : { title, body }
			},
		},
	],
	['reveal_attachment', { displayName: 'show attachment', icon: 'eye', inline: true }],
])

/**
 * tools that resolve an existing resource ref into inline content (file
 * readers). their content parts duplicate a resource ref rendered at its
 * origin, so the chat UI ignores their inline attachments.
 */
const resolverToolNames = new Set<string>(['file_get', 'reveal_attachment'])

/** returns true when a tool merely resolves an existing resource ref. */
export function isResolverTool(toolName: string): boolean {
	return resolverToolNames.has(toolName)
}

/** returns true when a tool has native display metadata. */
export function isNativeTool(toolName: string): boolean {
	return nativeTools.has(toolName)
}

/** returns true when a tool is backed by a remote MCP server. */
export function isMcpToolName(toolName: string): boolean {
	return toolName.startsWith('mcp_')
}

/** returns native display metadata for a tool, when registered. */
export function getNativeToolDefinition(toolName: string): NativeToolDefinition | null {
	return nativeTools.get(toolName) ?? null
}

/** returns the user-facing display name for a tool. */
export function getToolDisplayName(toolName: string): string {
	return getNativeToolDefinition(toolName)?.displayName ?? toolName.replace(/_/g, ' ')
}

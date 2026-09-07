import type { SettingsFieldDef, SettingsFieldGroup } from './types'

export const integrationsFields = {
	openWebUI: {
		id: 'open-webui',
		label: 'Open WebUI',
		description: 'import chats, memories, and notes from configured deployments.',
		keywords: ['import', 'api key', 'deployment'],
	},
	mcpServers: {
		id: 'mcp-servers',
		label: 'MCP servers',
		description: 'connect tools from servers you trust.',
		keywords: ['model context protocol', 'tools'],
	},
} satisfies SettingsFieldGroup

/** integrations that are declared but not connectable yet. */
export const pendingIntegrationFields: { field: SettingsFieldDef; origin: string }[] = [
	{
		field: {
			id: 'gemini',
			label: 'Gemini',
			description: 'import conversations from Gemini',
		},
		origin: 'https://gemini.google.com',
	},
	{
		field: {
			id: 'chatgpt',
			label: 'ChatGPT',
			description: 'import conversations from ChatGPT',
		},
		origin: 'https://chatgpt.com',
	},
	{
		field: {
			id: 'claude',
			label: 'Claude',
			description: 'import conversations from Claude',
		},
		origin: 'https://claude.com',
	},
]

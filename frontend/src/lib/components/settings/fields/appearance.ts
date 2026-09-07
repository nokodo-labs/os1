import type { SettingsFieldGroup } from './types'

export const appearanceFields = {
	theme: {
		id: 'theme',
		label: 'theme',
		description: 'choose light, dark, or auto which matches the theme to your wallpaper',
		keywords: ['light', 'dark', 'auto'],
	},
	autoAccentColors: {
		id: 'auto-accent-colors',
		label: 'auto accent colors',
		description: 'accent colors change automatically based on context',
	},
	accentColor: {
		id: 'accent-color',
		label: 'accent color',
		description: 'customize the accent color used for highlights and selection states',
	},
	wallpaper: {
		id: 'wallpaper',
		label: 'wallpaper',
		description: 'choose the app background for all devices or only this one',
		keywords: ['background'],
	},
	autoWallpaper: {
		id: 'auto-wallpaper',
		label: 'auto wallpaper',
		description: 'wallpaper changes automatically based on context',
	},
	chooseWallpaper: {
		id: 'choose-wallpaper',
		label: 'choose wallpaper',
		description: 'select a dynamic background for the app',
		keywords: ['static color', 'galaxy', 'clouds', 'silk', 'fog'],
	},
	chat: {
		id: 'chat',
		label: 'chat',
		description: 'how message bubbles look and move in your conversations',
		keywords: ['messages', 'bubbles', 'conversation'],
	},
	bubbleTails: {
		id: 'chat-bubble-tails',
		label: 'chat bubble tails',
		description:
			'add decorative tails to chat message bubbles, similar to popular messaging apps',
	},
	bubbleAnimation: {
		id: 'bubble-animation',
		label: 'bubble animation',
		description: 'how your outgoing message animates into the chat thread',
	},
	readReceipts: {
		id: 'read-receipts-style',
		label: 'read receipts style',
		description: 'ticks beside your message, or a word under the latest one',
		keywords: ['delivered', 'read', 'ticks'],
	},
} satisfies SettingsFieldGroup

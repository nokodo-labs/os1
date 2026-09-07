/**
 * settings/appearance: the chat card.
 *
 * every chat-scoped look setting lives in ONE card - bubble tails, bubble
 * animation and read receipt style are plain blocks inside it, never cards of
 * their own (the settings grammar forbids a card inside a card). each radio
 * option carries a glyph, and picking one still reaches the store behind it.
 */

import { fireEvent, render } from '@testing-library/svelte'
import { tick } from 'svelte'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn() }))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

vi.mock('$lib/contexts/systemChromeContext.svelte', () => ({
	useSystemChrome: () => ({ setContextActions: () => {} }),
}))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null, response: { ok: true } }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null, response: { ok: true } }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null, response: { ok: true } }),
		PUT: vi.fn().mockResolvedValue({ data: null, error: null, response: { ok: true } }),
	},
}))

const AppearancePage = (await import('../../routes/settings/appearance/+page.svelte')).default
const { preferences } = await import('$lib/stores/preferences.svelte')
const { readReceiptStyle, DEFAULT_READ_RECEIPT_STYLE } =
	await import('$lib/stores/readReceiptStyle.svelte')

/** the element `settingsFieldAnchor` marks for a field id. */
function field(id: string): HTMLElement {
	const el = document.body.querySelector(`[data-settings-field="${id}"]`)
	if (!(el instanceof HTMLElement)) throw new Error(`no settings field "${id}"`)
	return el
}

/** the radio pills of one field, in render order. */
function options(id: string): HTMLButtonElement[] {
	return [...field(id).querySelectorAll('[role="radio"]')].filter(
		(el): el is HTMLButtonElement => el instanceof HTMLButtonElement
	)
}

function optionLabelled(id: string, label: string): HTMLButtonElement {
	const match = options(id).find((el) => el.textContent?.trim() === label)
	if (!match) throw new Error(`no "${label}" option in "${id}"`)
	return match
}

async function renderPage(): Promise<void> {
	render(AppearancePage)
	await tick()
	await tick()
}

describe('settings/appearance chat options carry glyphs', () => {
	it('gives every bubble tail style an icon', async () => {
		await renderPage()
		const pills = options('chat-bubble-tails')
		expect(pills.map((el) => el.textContent?.trim())).toEqual(['none', 'whatsapp', 'imessage'])
		for (const pill of pills) expect(pill.querySelector('svg')).not.toBeNull()
	})

	it('gives every bubble animation an icon', async () => {
		await renderPage()
		const pills = options('bubble-animation')
		expect(pills.map((el) => el.textContent?.trim())).toEqual(['morph', 'fly up', 'none'])
		for (const pill of pills) expect(pill.querySelector('svg')).not.toBeNull()
	})

	it('gives both read receipt styles an icon', async () => {
		await renderPage()
		const pills = options('read-receipts-style')
		expect(pills.map((el) => el.textContent?.trim())).toEqual(['ticks', 'text'])
		for (const pill of pills) expect(pill.querySelector('svg')).not.toBeNull()
	})
})

describe('settings/appearance chat grouping', () => {
	it('holds all three chat settings in the one chat card', async () => {
		await renderPage()
		const chat = field('chat')
		expect(chat.classList.contains('liquid-glass')).toBe(true)
		for (const id of ['chat-bubble-tails', 'bubble-animation', 'read-receipts-style']) {
			expect(chat.contains(field(id))).toBe(true)
		}
	})

	it('keeps the grouped settings plain blocks, never cards inside a card', async () => {
		await renderPage()
		// the radio pills are glass too, so the card surface is what is counted
		expect(field('chat').querySelectorAll('.rounded-container.liquid-glass')).toHaveLength(0)
	})

	it('titles the card with its leading icon', async () => {
		await renderPage()
		// SettingsField wraps the `leading` snippet in its own shrink-0 slot
		expect(field('chat').querySelector('div.shrink-0 > svg')).not.toBeNull()
	})

	it('offers no receipts scope toggle until the synced field ships', async () => {
		await renderPage()
		const scoped = field('read-receipts-style').querySelector('[aria-pressed]')
		expect(scoped).toBeNull()
	})
})

describe('settings/appearance chat settings still switch', () => {
	beforeEach(() => {
		readReceiptStyle.set(DEFAULT_READ_RECEIPT_STYLE)
		vi.restoreAllMocks()
	})

	it('writes a picked tail style through the preferences store', async () => {
		const update = vi.spyOn(preferences, 'updateBubbleTailStyle').mockResolvedValue(true)
		await renderPage()
		await fireEvent.click(optionLabelled('chat-bubble-tails', 'whatsapp'))
		expect(update).toHaveBeenCalledWith('whatsapp')
	})

	it('writes a picked bubble animation through the preferences store', async () => {
		const update = vi.spyOn(preferences, 'updateBubbleAnimation').mockResolvedValue(true)
		await renderPage()
		await fireEvent.click(optionLabelled('bubble-animation', 'fly up'))
		expect(update).toHaveBeenCalledWith('flyup')
	})

	it('flips the local read receipt style and marks it selected', async () => {
		await renderPage()
		await fireEvent.click(optionLabelled('read-receipts-style', 'ticks'))
		await tick()

		expect(readReceiptStyle.style).toBe('ticks')
		expect(optionLabelled('read-receipts-style', 'ticks').getAttribute('aria-checked')).toBe(
			'true'
		)
	})
})

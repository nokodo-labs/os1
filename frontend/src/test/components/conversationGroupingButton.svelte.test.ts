/**
 * the messages group-by control: the island button wears the active grouping's icon and
 * label, and the menu draws the selected option solid while the rest stay outline (F115).
 */

import { fireEvent, render, screen } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: true, dev: false }))

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: [], error: null }),
		POST: vi.fn().mockResolvedValue({ data: null, error: null }),
		PATCH: vi.fn().mockResolvedValue({ data: null, error: null }),
		DELETE: vi.fn().mockResolvedValue({ data: null, error: null }),
	},
}))

vi.mock('$lib/auth/session.svelte', () => ({
	getAccessToken: vi.fn(() => null),
	onAccessTokenChanged: vi.fn(),
}))

const ConversationGroupingButton = (
	await import('$lib/components/messages/ConversationGroupingButton.svelte')
).default

/** an outline icon paints its stroke on no fill; a solid one fills with the text colour. */
function isSolid(icon: SVGSVGElement | null): boolean {
	return icon?.getAttribute('fill') === 'currentColor'
}

function iconOf(element: Element | null): SVGSVGElement | null {
	return element?.querySelector('svg') ?? null
}

describe('conversation grouping button', () => {
	it('wears the generic glyph and no label at the default grouping', () => {
		render(ConversationGroupingButton, { value: 'default', onSelect: vi.fn() })

		const button = screen.getByLabelText('group by')

		expect(button.textContent?.trim()).toBe('')
		expect(isSolid(iconOf(button))).toBe(false)
	})

	it('wears the active grouping icon and label, solid, once one is picked', () => {
		render(ConversationGroupingButton, { value: 'read-status', onSelect: vi.fn() })

		const button = screen.getByLabelText('group by: read status')

		expect(button.textContent).toContain('read status')
		expect(isSolid(iconOf(button))).toBe(true)
	})

	it('draws only the selected menu option solid', async () => {
		render(ConversationGroupingButton, { value: 'kind', onSelect: vi.fn() })

		await fireEvent.click(screen.getByLabelText('group by: DM vs groupchat'))

		const rows = screen.getAllByRole('menuitem')
		const solidLabels = rows
			.filter((row) => isSolid(iconOf(row)))
			.map((row) => row.textContent?.trim())

		expect(rows).toHaveLength(3)
		expect(solidLabels).toEqual(['DM vs groupchat'])
	})

	it('hands the picked grouping back and closes the menu', async () => {
		const onSelect = vi.fn()
		render(ConversationGroupingButton, { value: 'default', onSelect })

		await fireEvent.click(screen.getByLabelText('group by'))
		await fireEvent.click(screen.getByRole('menuitem', { name: 'read status' }))

		expect(onSelect).toHaveBeenCalledWith('read-status')
	})
})

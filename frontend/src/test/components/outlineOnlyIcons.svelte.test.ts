/**
 * a heavier stroke is not a solid variant. icons built purely from strokes - the sort
 * glyphs, the paperclip - have nothing to fill, so they stay outline-only and declare no
 * `variant` prop at all (F117). the selected row of a filter/sort menu still asks for
 * solid (F115); the ask has to land on the icon's single drawing rather than a faked
 * weight, while icons that do own a filled twin keep flipping.
 */

import SortIcon from '$lib/components/icons/SortIcon.svelte'
import { render, screen } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

const MenuIconVariantFixture = (await import('./MenuIconVariantFixture.svelte')).default

/** the glyph a menu row draws, minus the inert attribute an unclaimed ask leaves behind. */
function rowGlyph(name: string): string {
	const row = document.querySelector(`[data-row="${name}"]`)
	const svg = row?.querySelector('svg')
	if (!svg) throw new Error(`no icon rendered for ${name}`)
	svg.removeAttribute('variant')
	return svg.outerHTML
}

describe('menu rows and outline-only icons', () => {
	it.each(['sort', 'clip'])('draws %s the same selected as unselected', (icon) => {
		render(MenuIconVariantFixture)

		expect(rowGlyph(`${icon}-selected`)).toBe(rowGlyph(`${icon}-unselected`))
	})

	it('still flips an icon that owns a filled twin', () => {
		render(MenuIconVariantFixture)

		expect(rowGlyph('funnel-selected')).not.toBe(rowGlyph('funnel-unselected'))
	})

	it('marks the selected row selected either way', () => {
		render(MenuIconVariantFixture)

		const selected = screen
			.getAllByRole('menuitem')
			.filter((row) => row.getAttribute('data-row')?.endsWith('-selected'))
		expect(selected).toHaveLength(3)
	})

	it.each(['', 'name', 'created_at:desc', 'updated_at:asc', 'position', 'content_length:asc'])(
		'never thickens the sort glyph for %s in place of filling it',
		(value) => {
			const { container } = render(SortIcon, { value })
			const svg = container.querySelector('svg')

			expect(svg?.getAttribute('stroke-width')).toBe('1.7')
			expect(svg?.getAttribute('fill')).toBe('none')
		}
	)
})

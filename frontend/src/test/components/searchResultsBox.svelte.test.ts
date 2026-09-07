/**
 * the shared results surface: what home's autocomplete and every app-scoped
 * find bar hang over their input. sections, and the one navigation contract -
 * arrows walk the flattened run, enter takes the highlighted row, escape closes.
 */

import type { SearchResultsKeyHandler } from '$lib/components/common/SearchResultsBox.svelte'
import { fireEvent, render } from '@testing-library/svelte'
import { tick } from 'svelte'
import { describe, expect, it, vi } from 'vitest'
import SearchResultsBoxFixture from './SearchResultsBoxFixture.svelte'

interface Item {
	id: string
	label: string
}

const oneSection = [
	{
		id: 'all',
		items: [
			{ id: 'a', label: 'alpha' },
			{ id: 'b', label: 'beta' },
		],
	},
]

const twoSections = [
	{ id: 'conversations', label: 'conversations', items: [{ id: 'a', label: 'alpha' }] },
	{ id: 'requests', label: 'requests', items: [{ id: 'b', label: 'beta' }] },
]

async function mount(props: {
	sections: { id: string; label?: string; items: Item[] }[]
	query?: string
	onSelect?: (item: Item) => void
	onDismiss?: () => void
}) {
	let press: SearchResultsKeyHandler = () => false
	const rendered = render(SearchResultsBoxFixture, {
		props: { ...props, onKeyHandler: (handler) => (press = handler) },
	})
	await tick()

	function key(name: string): boolean {
		const consumed = press(new KeyboardEvent('keydown', { key: name, cancelable: true }))
		return consumed
	}

	return { ...rendered, key }
}

function highlighted(container: HTMLElement): string | null {
	return container.querySelector('[aria-selected="true"]')?.getAttribute('data-row') ?? null
}

describe('SearchResultsBox', () => {
	it('draws one labelled run per section, in order', async () => {
		const { container } = await mount({ sections: twoSections })

		const labels = [...container.querySelectorAll('[data-section-label]')].map((el) =>
			el.textContent?.trim()
		)
		expect(labels).toEqual(['conversations', 'requests'])
		expect(container.querySelectorAll('[data-row]')).toHaveLength(2)
	})

	it('leaves the header out of an unnamed run', async () => {
		const { container } = await mount({ sections: oneSection })

		expect(container.querySelector('[data-section-label]')).toBeNull()
		expect(container.querySelector('[data-search-results]')).not.toBeNull()
	})

	it('walks every section as one run, wrapping at both ends', async () => {
		const { container, key } = await mount({ sections: twoSections })

		expect(key('ArrowDown')).toBe(true)
		await tick()
		expect(highlighted(container)).toBe('a')

		key('ArrowDown')
		await tick()
		expect(highlighted(container)).toBe('b')

		key('ArrowDown')
		await tick()
		expect(highlighted(container)).toBe('a')

		key('ArrowUp')
		await tick()
		expect(highlighted(container)).toBe('b')
	})

	it('gives enter back to the input until the user has walked into the list', async () => {
		const onSelect = vi.fn()
		const { key } = await mount({ sections: oneSection, onSelect })

		expect(key('Enter')).toBe(false)
		expect(onSelect).not.toHaveBeenCalled()
	})

	it('takes the highlighted row on enter and closes behind it', async () => {
		const onSelect = vi.fn()
		const { container, key } = await mount({ sections: oneSection, onSelect })

		key('ArrowDown')
		key('ArrowDown')
		expect(key('Enter')).toBe(true)
		await tick()

		expect(onSelect).toHaveBeenCalledWith({ id: 'b', label: 'beta' })
		expect(container.querySelector('[data-search-results]')).toBeNull()
	})

	it('closes on escape and tells the caller, which is where the query is dropped', async () => {
		const onDismiss = vi.fn()
		const { container, key } = await mount({ sections: oneSection, onDismiss })

		expect(key('Escape')).toBe(true)
		await tick()

		expect(onDismiss).toHaveBeenCalledTimes(1)
		expect(container.querySelector('[data-search-results]')).toBeNull()
		// closed, so the keys belong to the input again
		expect(key('ArrowDown')).toBe(false)
	})

	it('re-opens on the next query, with nothing highlighted', async () => {
		const { container, rerender, key } = await mount({ sections: oneSection })

		key('ArrowDown')
		key('Escape')
		await tick()
		expect(container.querySelector('[data-search-results]')).toBeNull()

		await rerender({ query: 'ab', sections: oneSection })
		await tick()

		expect(container.querySelector('[data-search-results]')).not.toBeNull()
		expect(highlighted(container)).toBeNull()
	})

	it('takes a row on tap, and follows the pointer while it hovers', async () => {
		const onSelect = vi.fn()
		const { container } = await mount({ sections: oneSection, onSelect })
		const second = container.querySelector('[data-row="b"]')
		if (!second) throw new Error('row not rendered')

		await fireEvent.mouseEnter(second)
		expect(highlighted(container)).toBe('b')

		await fireEvent.click(second)
		expect(onSelect).toHaveBeenCalledWith({ id: 'b', label: 'beta' })
	})

	it('closes from the footer, so a trailing action can take over', async () => {
		const { container } = await mount({ sections: oneSection })
		const footer = container.querySelector('[data-footer]')
		if (!footer) throw new Error('footer not rendered')

		await fireEvent.click(footer)

		expect(container.querySelector('[data-search-results]')).toBeNull()
	})

	it('stays closed while there is nothing to show', async () => {
		const { container } = await mount({ sections: [{ id: 'all', items: [] }] })

		expect(container.querySelector('[data-search-results]')).toBeNull()
	})
})

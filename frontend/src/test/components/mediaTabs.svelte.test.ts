/**
 * the media app's tab island: four real routes behind one `(tabs)` group, the
 * same scaffold social uses. the active tab is whichever route is open, and it
 * is the only one drawn solid. the title names the app and the tab (F118).
 */

import { render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { beforeAll, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ pathname: '/media/discover' }))

vi.mock('$app/state', () => ({
	page: {
		get url() {
			return new URL(`https://nokodo.test${state.pathname}`)
		},
	},
}))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

beforeAll(() => {
	vi.stubGlobal(
		'ResizeObserver',
		class {
			observe() {}
			unobserve() {}
			disconnect() {}
		}
	)
})

const MediaTabsFixture = (await import('./MediaTabsFixture.svelte')).default

async function mountAt(pathname: string) {
	state.pathname = pathname
	const rendered = render(MediaTabsFixture)
	await tick()
	return rendered
}

function tabs(): HTMLAnchorElement[] {
	const nav = screen.getByLabelText('section navigation')
	return [...nav.querySelectorAll('a')]
}

function isSolid(tab: HTMLAnchorElement): boolean {
	return tab.querySelector('svg')?.getAttribute('fill') === 'currentColor'
}

describe('media tab island', () => {
	it('renders the four tabs in order, each with an icon', async () => {
		await mountAt('/media/discover')

		const rendered = tabs()
		expect(rendered.map((tab) => tab.textContent?.trim())).toEqual([
			'discover',
			'search',
			'movies',
			'shows',
		])
		expect(rendered.map((tab) => tab.getAttribute('href'))).toEqual([
			'/media/discover',
			'/media/search',
			'/media/movies',
			'/media/shows',
		])
		for (const tab of rendered) expect(tab.querySelector('svg')).not.toBeNull()
	})

	it.each([
		['/media/discover', 'media · discover'],
		['/media/search', 'media · search'],
		['/media/movies', 'media · movies'],
		['/media/shows', 'media · shows'],
	])('titles %s with the app and the tab', async (pathname, title) => {
		await mountAt(pathname)

		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(title)
	})

	it.each([
		['/media/discover', 0],
		['/media/search', 1],
		['/media/movies', 2],
		['/media/shows', 3],
	])('marks the tab for %s active', async (pathname, activeIndex) => {
		await mountAt(pathname)

		const rendered = tabs()
		rendered.forEach((tab, index) => {
			expect(tab.getAttribute('aria-current')).toBe(index === activeIndex ? 'page' : null)
			expect(isSolid(tab)).toBe(index === activeIndex)
		})
	})

	it('falls back to discover on the group root', async () => {
		await mountAt('/media')

		expect(tabs()[0].getAttribute('aria-current')).toBe('page')
	})
})

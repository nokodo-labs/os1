/**
 * social's tab island carries the same title as media's: one heading naming the app
 * and the tab you are in, drawn with the app glyph, hoisted out of the per-tab pages
 * into the `(tabs)` layout so it survives a tab change (F118).
 */

import { render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { beforeAll, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ pathname: '/social/friends' }))

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

const SocialTabsFixture = (await import('./SocialTabsFixture.svelte')).default

async function mountAt(pathname: string) {
	state.pathname = pathname
	const rendered = render(SocialTabsFixture)
	await tick()
	return rendered
}

function tabs(): HTMLAnchorElement[] {
	const nav = screen.getByLabelText('section navigation')
	return [...nav.querySelectorAll('a')]
}

describe('social tab island', () => {
	it.each([
		['/social/friends', 'social · friends'],
		['/social/groups', 'social · groups'],
	])('titles %s with the app and the tab', async (pathname, title) => {
		await mountAt(pathname)

		expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(title)
	})

	it('keeps a single title for the whole app, not one per page', async () => {
		await mountAt('/social/groups')

		expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
	})

	it.each([
		['/social/friends', 0],
		['/social/groups', 1],
	])('marks the tab for %s active', async (pathname, activeIndex) => {
		await mountAt(pathname)

		tabs().forEach((tab, index) => {
			expect(tab.getAttribute('aria-current')).toBe(index === activeIndex ? 'page' : null)
		})
	})
})

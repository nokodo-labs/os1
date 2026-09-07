/**
 * the notes sidebar's "no notes yet" state has to fill the list area so it
 * lands in the vertical middle, in both compact and regular layouts.
 */

import { render } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/navigation', () => ({ goto: vi.fn().mockResolvedValue(undefined) }))

vi.mock('$app/paths', () => ({ base: '', resolve: (path: string) => path }))

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

vi.mock('$lib/stores/notes.svelte', () => ({
	notes: {
		all: [],
		hydrated: true,
		loading: false,
		sortMode: 'updated_at:desc',
		load: vi.fn().mockResolvedValue([]),
		create: vi.fn().mockResolvedValue(null),
		update: vi.fn().mockResolvedValue(null),
		remove: vi.fn().mockResolvedValue(true),
		get: vi.fn(() => null),
	},
}))

vi.mock('$lib/stores/projects.svelte', () => ({
	projects: {
		list: [],
		load: vi.fn().mockResolvedValue([]),
		invalidateResourceCounts: vi.fn(),
	},
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		currentUserId: 'user_me',
		authorLabel: () => null,
		ensureUsers: vi.fn().mockResolvedValue(undefined),
	},
}))

vi.mock('$lib/stores/resourceAccess.svelte', () => ({
	resourceAccess: {
		version: 0,
		level: () => 'owner',
		ensure: vi.fn().mockResolvedValue(undefined),
	},
	canEditAccessLevel: () => true,
	canDeleteAccessLevel: () => true,
}))

const NotesSidebar = (await import('$lib/components/notes/NotesSidebar.svelte')).default

function renderSidebar(isMobile: boolean) {
	return render(NotesSidebar, { props: { selectedNoteId: null, isMobile } })
}

describe('NotesSidebar empty state', () => {
	for (const [layout, isMobile] of [
		['compact', true],
		['regular', false],
	] as const) {
		it(`stretches the empty state over the free list height in ${layout}`, () => {
			const { container } = renderSidebar(isMobile)

			const emptyState = container.querySelector('[data-empty-state]')
			expect(emptyState).not.toBeNull()
			expect(emptyState?.getAttribute('data-empty-state-label')).toBe('no notes yet')

			// the empty state centers its own content, so it only has to be given the height
			expect(emptyState?.className).toContain('justify-center')
			expect(emptyState?.className).toContain('flex-1')

			// ...which its wrapper passes down from the flex-1 list column
			const wrapper = emptyState?.parentElement
			expect(wrapper?.className).toContain('flex-1')
			expect(wrapper?.className).toContain('flex-col')

			const nav = wrapper?.closest('nav')
			expect(nav?.className).toContain('flex-1')
		})
	}
})

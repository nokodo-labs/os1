import { searchProjectResources } from '$lib/resources/projectSearch'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
	GET: vi.fn(),
	POST: vi.fn(),
	PATCH: vi.fn(),
	DELETE: vi.fn(),
}))

vi.mock('$lib/api/client', () => ({
	api: apiMocks,
	getApiBaseUrl: vi.fn(() => 'http://localhost:1383'),
}))

function threadPage() {
	return {
		data: {
			items: [
				{
					id: 'thread_1',
					title: 'launch plan',
					owner_id: 'user_1',
					tags: ['plan'],
					project_ids: ['project_1'],
					is_temporary: false,
					created_at: '2025-01-01T00:00:00.000Z',
					updated_at: '2025-01-02T00:00:00.000Z',
					last_activity_at: '2025-01-03T00:00:00.000Z',
				},
			],
			has_more: false,
		},
		error: null,
	}
}

function notePage() {
	return {
		data: {
			items: [
				{
					id: 'note_1',
					title: 'launch checklist',
					content: 'ship it',
					labels: ['launch'],
					project_ids: ['project_1'],
					user_id: 'user_1',
					created_at: '2025-01-01T00:00:00.000Z',
					updated_at: '2025-01-05T00:00:00.000Z',
				},
			],
			has_more: false,
		},
		error: null,
	}
}

beforeEach(() => {
	apiMocks.GET.mockReset()
	apiMocks.GET.mockImplementation((path: string) =>
		Promise.resolve(path === '/v1/threads/search' ? threadPage() : notePage())
	)
})

describe('searchProjectResources', () => {
	it('scopes both endpoints to the project and stays on active branches', async () => {
		await searchProjectResources({ query: 'launch', projectId: 'project_1', limit: 5 })

		expect(apiMocks.GET).toHaveBeenCalledWith(
			'/v1/threads/search',
			expect.objectContaining({
				params: {
					query: {
						q: 'launch',
						limit: 5,
						project_id: 'project_1',
						include_all_branches: false,
					},
				},
			})
		)
		expect(apiMocks.GET).toHaveBeenCalledWith(
			'/v1/notes/search',
			expect.objectContaining({
				params: { query: { q: 'launch', limit: 5, project_id: 'project_1' } },
			})
		)
	})

	it('merges both kinds newest first', async () => {
		const results = await searchProjectResources({ query: 'launch', projectId: 'project_1' })

		expect(results.map((result) => result.id)).toEqual(['note_1', 'thread_1'])
		expect(results[0].href).toBe('/notes/note_1')
		expect(results[1].href).toBe('/c/thread_1')
	})

	it('asks only the endpoints the selected types cover', async () => {
		const results = await searchProjectResources({
			query: 'launch',
			projectId: 'project_1',
			types: ['note'],
		})

		expect(apiMocks.GET).toHaveBeenCalledTimes(1)
		expect(apiMocks.GET).toHaveBeenCalledWith('/v1/notes/search', expect.anything())
		expect(results.map((result) => result.type)).toEqual(['note'])
	})

	it('reaches inactive branches only when explicitly asked', async () => {
		await searchProjectResources({
			query: 'launch',
			projectId: 'project_1',
			types: ['thread'],
			includeAllBranches: true,
		})

		expect(apiMocks.GET).toHaveBeenCalledWith(
			'/v1/threads/search',
			expect.objectContaining({
				params: expect.objectContaining({
					query: expect.objectContaining({ include_all_branches: true }),
				}),
			})
		)
	})
})

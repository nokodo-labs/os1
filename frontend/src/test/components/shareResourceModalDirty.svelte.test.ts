/**
 * the share modal joins the shared dirty gate: save only ever writes the access
 * rules, so its button stays inert until the people list differs from the one
 * the modal opened with - and goes inert again when the change is undone.
 */

import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
import { fireEvent, render } from '@testing-library/svelte'
import { tick } from 'svelte'
import { describe, expect, it, vi } from 'vitest'

vi.mock('$app/environment', () => ({ browser: false, dev: false }))

vi.mock('$app/paths', () => ({ base: '' }))

vi.mock('$lib/api/client', () => ({
	api: { GET: vi.fn().mockResolvedValue({ data: [], error: null }) },
}))

vi.mock('$lib/stores/friends.svelte', () => ({
	friends: { list: [], load: () => Promise.resolve() },
}))

vi.mock('$lib/stores/groups.svelte', () => ({
	groups: { list: [], load: () => Promise.resolve() },
}))

vi.mock('$lib/stores/files.svelte', () => ({
	files: { get: () => null, load: () => Promise.resolve() },
	downloadFile: () => Promise.resolve(),
}))

vi.mock('$lib/stores/notifications.svelte', () => ({
	notifications: { pushEphemeralToast: vi.fn() },
	showError: vi.fn(),
}))

const replaceRules = vi.fn().mockResolvedValue([])

vi.mock('$lib/stores/resourceAccess.svelte', () => ({
	canShareAccessLevel: () => true,
	canEditAccessLevel: () => true,
	resourceAccess: {
		version: 0,
		level: () => 'admin',
		ensure: () => Promise.resolve(),
		ensureRules: () =>
			Promise.resolve([
				{
					id: 'rule_1',
					subject_user_id: 'user_alice',
					subject_group_id: null,
					subject_role_id: null,
					level: 'reader',
					order_index: 0,
				},
			]),
		replaceRules: (...args: unknown[]) => replaceRules(...args),
	},
}))

const ShareResourceModal = (await import('$lib/components/modals/ShareResourceModal.svelte'))
	.default

const payload: ResourceAccessPayload = {
	resourceType: 'note',
	resourceId: 'note_1',
	title: 'trip plan',
}

/** the modal portals into the body, so its buttons live outside the render container. */
function buttonLabelled(text: string): HTMLButtonElement | null {
	const buttons = [...document.body.querySelectorAll('button')]
	return buttons.find((el) => el.textContent?.trim() === text) ?? null
}

async function openModal(): Promise<HTMLButtonElement> {
	render(ShareResourceModal, { props: { open: true, payload, onClose: () => {} } })
	await vi.waitFor(() => {
		expect(buttonLabelled('can view')).not.toBeNull()
	})
	const save = buttonLabelled('save')
	expect(save).not.toBeNull()
	if (!save) throw new Error('missing save button')
	return save
}

async function pickLevel(label: string): Promise<void> {
	const button = buttonLabelled(label)
	if (!button) throw new Error(`missing level button ${label}`)
	await fireEvent.click(button)
	await tick()
}

describe('ShareResourceModal', () => {
	it('opens clean, so save is inert with the reason spoken', async () => {
		const save = await openModal()

		expect(save.getAttribute('aria-disabled')).toBe('true')
		expect(save.getAttribute('aria-label')).toBe('save, no changes to save')
	})

	it('enables save once an access level changes', async () => {
		const save = await openModal()
		await pickLevel('can edit')

		expect(save.getAttribute('aria-disabled')).toBe('false')
	})

	it('goes inert again when the change is undone', async () => {
		const save = await openModal()
		await pickLevel('can edit')
		expect(save.getAttribute('aria-disabled')).toBe('false')

		await pickLevel('can view')

		expect(save.getAttribute('aria-disabled')).toBe('true')
	})

	it('refuses to save a pristine form', async () => {
		replaceRules.mockClear()
		const save = await openModal()

		await fireEvent.click(save)
		await tick()

		expect(replaceRules).not.toHaveBeenCalled()
	})
})

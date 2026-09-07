/**
 * the reminder list modals join the shared dirty gate: their save button stays
 * inert, and says why, until the form differs from what it opened with.
 */

import { fireEvent, render } from '@testing-library/svelte'
import { tick } from 'svelte'
import { describe, expect, it, vi } from 'vitest'

vi.mock('$lib/stores/session.svelte', () => ({
	session: {
		currentUserId: 'user_1',
		authorLabel: () => 'me',
		ensureUsers: () => Promise.resolve(),
	},
}))

vi.mock('$lib/stores/resourceAccess.svelte', () => ({
	canEditAccessLevel: () => true,
	resourceAccess: {
		version: 0,
		level: () => 'admin',
		ensure: () => Promise.resolve(),
	},
}))

import ReminderListCreateModal from '$lib/components/reminders/ReminderListCreateModal.svelte'
import ReminderListPropertiesModal from '$lib/components/reminders/ReminderListPropertiesModal.svelte'
import type { ReminderListWithCounts } from '$lib/stores/reminders.svelte'

const list: ReminderListWithCounts = {
	id: 'reminder_list_1',
	owner_id: 'user_1',
	name: 'groceries',
	description: 'weekly run',
	icon: '',
	color: '#d45446',
	position: 0,
	is_default: false,
	project_ids: [],
	metadata: {},
	created_at: '2026-08-01T00:00:00Z',
	updated_at: '2026-08-01T00:00:00Z',
	total_count: 2,
	pending_count: 1,
	completed_count: 1,
}

/** the modals portal into the body, so the row lives outside the render container. */
function saveButton(label: string): HTMLButtonElement | null {
	const buttons = [...document.body.querySelectorAll('button')]
	return buttons.find((el) => el.textContent?.trim() === label) ?? null
}

async function typeInto(inputId: string, value: string): Promise<void> {
	const input = document.body.querySelector(`#${inputId}`)
	if (!(input instanceof HTMLInputElement)) throw new Error(`missing input ${inputId}`)
	await fireEvent.input(input, { target: { value } })
	await tick()
}

describe('ReminderListPropertiesModal', () => {
	it('opens clean, so save is inert with the reason spoken', async () => {
		render(ReminderListPropertiesModal, { props: { open: true, list, onClose: () => {} } })
		await tick()

		const el = saveButton('save')
		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('aria-label')).toBe('save, no changes to save')
		expect(el?.hasAttribute('disabled')).toBe(false)
	})

	it('enables save once a field changes', async () => {
		render(ReminderListPropertiesModal, { props: { open: true, list, onClose: () => {} } })
		await tick()
		await typeInto('list-name', 'groceries and more')

		const el = saveButton('save')
		expect(el?.getAttribute('aria-disabled')).toBe('false')
	})

	it('blocks an emptied name with its own reason', async () => {
		render(ReminderListPropertiesModal, { props: { open: true, list, onClose: () => {} } })
		await tick()
		await typeInto('list-name', '   ')

		const el = saveButton('save')
		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('title')).toBe('name is required')
	})
})

describe('ReminderListCreateModal', () => {
	it('opens with an untouched form, so create is inert', async () => {
		render(ReminderListCreateModal, { props: { open: true, onClose: () => {} } })
		await tick()

		const el = saveButton('create')
		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('title')).toBe('name is required')
	})

	it('enables create once the list is named', async () => {
		render(ReminderListCreateModal, { props: { open: true, onClose: () => {} } })
		await tick()
		await typeInto('new-list-name', 'trip')

		const el = saveButton('create')
		expect(el?.getAttribute('aria-disabled')).toBe('false')
	})
})

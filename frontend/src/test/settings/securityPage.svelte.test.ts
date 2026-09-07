/**
 * settings/security: the change-password form and the logout-all action.
 *
 * the form mirrors the backend rules (current password required, new password
 * at least 8 characters) plus its own confirm field, and its submit stays inert
 * until the form is both valid and dirty. logging out every session is
 * destructive and never fires straight off the button - it goes through the
 * shared confirm dialog first.
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

const post = vi.fn()

vi.mock('$lib/api/client', () => ({
	api: {
		GET: vi.fn().mockResolvedValue({ data: null, error: null, response: { ok: true } }),
		POST: (...args: unknown[]) => post(...args),
	},
}))

const logoutAndRedirect = vi.fn().mockResolvedValue(undefined)

vi.mock('$lib/auth/logout', () => ({ logoutAndRedirect: () => logoutAndRedirect() }))

vi.mock('$lib/auth/sessionRevocation', () => ({
	deferRevocationLogout: vi.fn(),
	cancelRevocationLogoutDefer: vi.fn(),
}))

vi.mock('$lib/stores/session.svelte', () => ({
	session: { currentUser: { id: 'user_me', email: 'me@nokodo.net' } },
}))

const SecurityPage = (await import('../../routes/settings/security/+page.svelte')).default
const { modals } = await import('$lib/stores/modals.svelte')

function buttonLabelled(text: string): HTMLButtonElement | null {
	const buttons = [...document.body.querySelectorAll('button')]
	return buttons.find((el) => el.textContent?.trim() === text) ?? null
}

function input(id: string): HTMLInputElement {
	const el = document.body.querySelector(`#${id}`)
	if (!(el instanceof HTMLInputElement)) throw new Error(`no input #${id}`)
	return el
}

async function type(id: string, value: string): Promise<void> {
	await fireEvent.input(input(id), { target: { value } })
	await tick()
}

async function renderPage(): Promise<void> {
	render(SecurityPage)
	await tick()
	await tick()
}

async function fillValidForm(): Promise<void> {
	await type('current-password', 'oldsecret1')
	await type('new-password', 'newsecret1')
	await type('confirm-password', 'newsecret1')
}

describe('settings/security change password', () => {
	beforeEach(() => {
		post.mockReset()
		post.mockResolvedValue({ data: null, error: null, response: { ok: true } })
		logoutAndRedirect.mockClear()
		modals.close()
	})

	it('keeps submit inert while the form is pristine', async () => {
		await renderPage()
		expect(buttonLabelled('update password')?.disabled).toBe(true)
	})

	it('keeps submit inert until every rule passes', async () => {
		await renderPage()
		await type('current-password', 'oldsecret1')
		expect(buttonLabelled('update password')?.disabled).toBe(true)

		// mirrors the backend min_length=8 on new_password
		await type('new-password', 'short')
		await type('confirm-password', 'short')
		expect(buttonLabelled('update password')?.disabled).toBe(true)

		await type('new-password', 'newsecret1')
		expect(buttonLabelled('update password')?.disabled).toBe(true)

		await type('confirm-password', 'newsecret1')
		expect(buttonLabelled('update password')?.disabled).toBe(false)
	})

	it('names the broken rule once a field has been visited', async () => {
		await renderPage()
		await type('new-password', 'short')
		await fireEvent.blur(input('new-password'))
		await tick()
		expect(document.body.textContent).toContain('new password must be at least 8 characters')

		await type('new-password', 'newsecret1')
		await type('confirm-password', 'newsecret2')
		await fireEvent.blur(input('confirm-password'))
		await tick()
		expect(document.body.textContent).toContain('passwords do not match')
	})

	it('posts the change and confirms it in place', async () => {
		await renderPage()
		await fillValidForm()
		await fireEvent.click(buttonLabelled('update password') as HTMLButtonElement)
		await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1))
		await tick()

		expect(post.mock.calls[0][0]).toBe('/v1/users/{user_id}/change-password')
		expect(post.mock.calls[0][1]).toMatchObject({
			body: { current_password: 'oldsecret1', new_password: 'newsecret1' },
		})
		expect(document.body.textContent).toContain('password updated')
		expect(buttonLabelled('update password')?.disabled).toBe(true)
	})

	it('surfaces a server error inline, next to the field it names', async () => {
		post.mockResolvedValue({
			data: null,
			error: { detail: 'current password is incorrect' },
			response: { ok: false },
		})
		await renderPage()
		await fillValidForm()
		await fireEvent.click(buttonLabelled('update password') as HTMLButtonElement)
		await vi.waitFor(() =>
			expect(document.body.textContent).toContain('current password is incorrect')
		)
		expect(document.body.textContent).not.toContain('password updated')
	})

	it('surfaces an unattributed server error above the fields', async () => {
		post.mockResolvedValue({
			data: null,
			error: { detail: 'user not found' },
			response: { ok: false },
		})
		await renderPage()
		await fillValidForm()
		await fireEvent.click(buttonLabelled('update password') as HTMLButtonElement)
		await vi.waitFor(() => expect(document.body.textContent).toContain('user not found'))
	})
})

describe('settings/security follows the settings grammar', () => {
	it('gives every section title its leading icon', async () => {
		await renderPage()
		// SettingsField wraps the `leading` snippet in its own shrink-0 slot
		const icons = document.body.querySelectorAll('div.shrink-0 > svg')
		expect(icons).toHaveLength(4)
	})

	it('submits full width with an icon, like every other settings action', async () => {
		await renderPage()
		const submit = buttonLabelled('update password')
		expect(submit?.classList.contains('w-full')).toBe(true)
		expect(submit?.querySelector('svg')).not.toBeNull()
	})

	it('keeps logging out every session a row in the session card, never a nested card', async () => {
		await renderPage()
		const revoke = buttonLabelled('log out all sessions')
		// a direct child of the glass card: no second card wraps it
		expect(revoke?.parentElement?.classList.contains('liquid-glass')).toBe(true)
		expect(revoke?.classList.contains('w-full')).toBe(true)
		expect(revoke?.querySelector('svg')).not.toBeNull()
	})
})

describe('settings/security logout all sessions', () => {
	beforeEach(() => {
		post.mockReset()
		post.mockResolvedValue({ data: null, error: null, response: { ok: true } })
		logoutAndRedirect.mockClear()
		modals.close()
	})

	it('asks for confirmation before revoking anything', async () => {
		await renderPage()
		await fireEvent.click(buttonLabelled('log out all sessions') as HTMLButtonElement)
		await tick()

		expect(modals.isOpen('confirm-delete')).toBe(true)
		expect(modals.confirmDeletePayload?.confirmLabel).toBe('log out everywhere')
		expect(post).not.toHaveBeenCalled()
	})

	it('calls the revoke endpoint only from the confirm step', async () => {
		await renderPage()
		await fireEvent.click(buttonLabelled('log out all sessions') as HTMLButtonElement)
		await tick()

		await modals.confirmDeletePayload?.onDelete(false)
		expect(post).toHaveBeenCalledTimes(1)
		expect(post.mock.calls[0][0]).toBe('/v1/users/{user_id}/sessions/revoke')
		expect(post.mock.calls[0][1]).toMatchObject({ params: { path: { user_id: 'user_me' } } })
		expect(logoutAndRedirect).toHaveBeenCalledTimes(1)
	})

	it('reports a failed revoke on the page', async () => {
		post.mockResolvedValue({
			data: null,
			error: { detail: 'forbidden' },
			response: { ok: false },
		})
		await renderPage()
		await fireEvent.click(buttonLabelled('log out all sessions') as HTMLButtonElement)
		await tick()

		await modals.confirmDeletePayload?.onDelete(false)
		await tick()
		expect(document.body.textContent).toContain('forbidden')
		expect(logoutAndRedirect).not.toHaveBeenCalled()
	})
})

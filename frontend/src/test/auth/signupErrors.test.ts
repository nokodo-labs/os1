import { describe, expect, it } from 'vitest'

import { parseSignupBackendErrors, signupSubmissionErrorMessage } from '$lib/auth/signupErrors'

describe('signup error helpers', () => {
	it('maps duplicate username messages to the username field', () => {
		const parsed = parseSignupBackendErrors('username already taken')

		expect(parsed.message).toBeNull()
		expect(parsed.fields).toEqual({ username: 'username already taken' })
	})

	it('maps duplicate email messages to the email field', () => {
		const parsed = parseSignupBackendErrors('email already registered')

		expect(parsed.message).toBeNull()
		expect(parsed.fields).toEqual({ email: 'email already registered' })
	})

	it('uses a stable message for masked fetch failures', () => {
		expect(signupSubmissionErrorMessage(new TypeError('Failed to fetch'))).toBe(
			'could not reach the server. try again in a moment.'
		)
	})
})

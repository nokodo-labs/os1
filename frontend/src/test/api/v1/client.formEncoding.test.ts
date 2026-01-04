import createClient from 'openapi-fetch'
import { describe, expect, it } from 'vitest'

import type { paths } from '$lib/api/types'

describe('v1 auth login form encoding', () => {
	it('encodes application/x-www-form-urlencoded bodies', async () => {
		let capturedRequest: Request | undefined

		const client = createClient<paths>({
			baseUrl: 'http://example.test/v1',
			fetch: async (input: RequestInfo | URL) => {
				capturedRequest = input instanceof Request ? input : new Request(input)
				return new Response(JSON.stringify({ access_token: 't', token_type: 'bearer' }), {
					status: 200,
					headers: { 'Content-Type': 'application/json' },
				})
			},
		})

		await client.POST('/auth/login/access-token', {
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded',
			},
			body: {
				username: 'user@nokodo.net',
				password: 'pass',
				scope: '',
			},
		})

		expect(capturedRequest).toBeTruthy()
		expect(capturedRequest?.headers.get('Content-Type')).toBe(
			'application/x-www-form-urlencoded'
		)

		const body = await capturedRequest!.text()
		const params = new URLSearchParams(body)
		expect(params.get('username')).toBe('user@nokodo.net')
		expect(params.get('password')).toBe('pass')
		expect(params.get('scope')).toBe('')
	})
})

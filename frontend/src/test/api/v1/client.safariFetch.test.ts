import { afterEach, describe, expect, it, vi } from 'vitest'

describe('api client safari fetch compatibility', () => {
	afterEach(() => {
		vi.unstubAllGlobals()
		vi.resetModules()
	})

	it('unwraps https Request bodies before native fetch', async () => {
		const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = []
		vi.stubGlobal(
			'fetch',
			vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
				calls.push({ input, init })

				const url =
					typeof input === 'string'
						? input
						: input instanceof URL
							? input.toString()
							: input.url

				if (url === '/config.json') {
					return new Response(
						JSON.stringify({ api_origin: 'https://api.example.test' }),
						{
							status: 200,
							headers: { 'Content-Type': 'application/json' },
						}
					)
				}

				return new Response(JSON.stringify({ access_token: 't', token_type: 'bearer' }), {
					status: 200,
					headers: { 'Content-Type': 'application/json' },
				})
			})
		)

		const { rawApi } = await import('$lib/api/client')

		await rawApi.POST('/v1/auth/login/access-token', {
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded',
			},
			body: {
				username: 'user@nokodo.net',
				password: 'pass',
				scope: '',
			},
		})

		const loginCall = calls.find((call) => {
			const input = call.input
			const url =
				typeof input === 'string'
					? input
					: input instanceof URL
						? input.toString()
						: input.url
			return url === 'https://api.example.test/v1/auth/login/access-token'
		})

		expect(loginCall).toBeTruthy()
		expect(loginCall?.input).toBe('https://api.example.test/v1/auth/login/access-token')
		expect(loginCall?.init?.body).toBeInstanceOf(Blob)

		const body = await (loginCall!.init!.body as Blob).text()
		const params = new URLSearchParams(body)
		expect(params.get('username')).toBe('user@nokodo.net')
		expect(params.get('password')).toBe('pass')
		expect(params.get('scope')).toBe('')
	})
})

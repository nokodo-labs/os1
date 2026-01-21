export type SystemStatusResponse = {
	initialized: boolean
}

const DEFAULT_API_BASE = 'http://localhost:1383/v1'

function getSystemBaseUrl(): string {
	const apiBase = import.meta.env.VITE_API_URL || DEFAULT_API_BASE
	if (apiBase.endsWith('/v1')) return apiBase.slice(0, -3)
	return apiBase
}

async function authHeaders(): Promise<HeadersInit> {
	if (typeof localStorage === 'undefined') return { Accept: 'application/json' }

	const token = localStorage.getItem('access_token')
	if (!token) return { Accept: 'application/json' }

	return {
		Accept: 'application/json',
		Authorization: `Bearer ${token}`,
	}
}

export class SystemService {
	static async getSystemStatus(): Promise<SystemStatusResponse> {
		const base = getSystemBaseUrl()
		const response = await fetch(`${base}/system/status`, {
			method: 'GET',
			headers: await authHeaders(),
		})

		if (!response.ok) {
			throw new Error(`failed to fetch system status: ${response.status}`)
		}

		return response.json() as Promise<SystemStatusResponse>
	}
}

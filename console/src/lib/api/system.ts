export type SystemStatusResponse = {
	initialized: boolean
}

const DEFAULT_API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:1383'

export class SystemService {
	static async getSystemStatus(): Promise<SystemStatusResponse> {
		const response = await fetch(`${DEFAULT_API_BASE}/system/status`, {
			method: 'GET',
			headers: { Accept: 'application/json' },
			credentials: 'include',
		})

		if (!response.ok) {
			throw new Error(`failed to fetch system status: ${response.status}`)
		}

		return response.json() as Promise<SystemStatusResponse>
	}
}

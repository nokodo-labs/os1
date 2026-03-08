import { apiOriginReady, getApiOrigin } from './origin'

export type SystemStatusResponse = {
	initialized: boolean
}

export class SystemService {
	static async getSystemStatus(): Promise<SystemStatusResponse> {
		await apiOriginReady
		const response = await fetch(`${getApiOrigin()}/system/status`, {
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

import { apiOriginReady, getApiOrigin } from './origin'

export type SystemStatus = { initialized: boolean }

export async function getSystemStatus(): Promise<SystemStatus> {
	await apiOriginReady
	const base = getApiOrigin()
	if (!base) throw new Error('api origin not initialized')

	const res = await fetch(`${base}/system/status`, {
		headers: { Accept: 'application/json' },
		credentials: 'include',
	})

	if (!res.ok) throw new Error('failed to fetch system status')

	const data = await res.json()
	if (typeof data?.initialized !== 'boolean') {
		throw new Error('invalid system status response')
	}

	return { initialized: data.initialized }
}

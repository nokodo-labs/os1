import { getApiBaseUrl } from './client'
import { apiOriginReady } from './init'

export type SystemStatus = {
	initialized: boolean
}

export async function getSystemStatus(): Promise<SystemStatus> {
	await apiOriginReady

	const configuredBaseUrl = getApiBaseUrl()
	const httpBase = configuredBaseUrl || window.location.origin

	const response = await fetch(`${httpBase}/system/status`, {
		method: 'GET',
		headers: { Accept: 'application/json' },
		credentials: 'include',
	})

	if (!response.ok) throw new Error('failed to check system status')

	const data: unknown = await response.json()
	if (!data || typeof data !== 'object') throw new Error('failed to check system status')

	const initialized = (data as { initialized?: unknown }).initialized
	if (typeof initialized !== 'boolean') throw new Error('failed to check system status')

	return { initialized }
}

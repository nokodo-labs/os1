import type { components } from './types'
import { v1Client } from './v1/client'

type User = components['schemas']['User']
type UserCreate = components['schemas']['UserCreate']
type RuntimeConfig = components['schemas']['RuntimeConfigOut']

// Root health is not part of the v1 OpenAPI schema.
type HealthCheck = { status: string }

class APIError extends Error {
	constructor(
		message: string,
		public status: number,
		public response?: unknown
	) {
		super(message)
		this.name = 'APIError'
	}
}

export const api = {
	async healthCheck(): Promise<HealthCheck> {
		const response = await fetch('/health')
		if (!response.ok) {
			throw new APIError(response.statusText, response.status)
		}
		return response.json()
	},

	async getUsers(params?: { skip?: number; limit?: number }): Promise<User[]> {
		const { data, error, response } = await v1Client().GET('/users', {
			params: params ? { query: params } : undefined,
		})
		if (error) throw new APIError(response.statusText, response.status, error)
		return data ?? []
	},

	async getUser(id: string): Promise<User> {
		const { data, error, response } = await v1Client().GET('/users/{user_id}', {
			params: { path: { user_id: id } },
		})
		if (error || !data) throw new APIError(response.statusText, response.status, error)
		return data
	},

	async createUser(userData: UserCreate): Promise<User> {
		const { data, error, response } = await v1Client().POST('/users', {
			body: userData,
		})
		if (error || !data) throw new APIError(response.statusText, response.status, error)
		return data
	},

	async getRuntimeConfig(): Promise<RuntimeConfig> {
		const { data, error } = await v1Client().GET('/system/config')
		if (error) throw new APIError('failed to load runtime config', 0, error)
		return data
	},
}

export { APIError }
export type { HealthCheck, RuntimeConfig, User, UserCreate }

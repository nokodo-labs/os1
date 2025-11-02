import { apiClient, APIError } from './client';
import type { HealthCheck, User, UserCreate } from './types';

export const api = {
	async healthCheck(): Promise<HealthCheck> {
		return apiClient.get<HealthCheck>('/health')
	},

	async getUsers(params?: { skip?: number; limit?: number }): Promise<User[]> {
		return apiClient.get<User[]>('/users', { params })
	},

	async getUser(id: number): Promise<User> {
		return apiClient.get<User>(`/users/${id}`)
	},

	async createUser(userData: UserCreate): Promise<User> {
		return apiClient.post<User>('/users', userData)
	},
}

export { apiClient, APIError };
export type { HealthCheck, User, UserCreate };


type FetchOptions = RequestInit & {
	params?: Record<string, string | number>
}

class APIError extends Error {
	constructor(
		message: string,
		public status: number,
		public response?: unknown,
	) {
		super(message)
		this.name = 'APIError'
	}
}

class APIClient {
	private baseURL: string

	constructor(baseURL: string = import.meta.env.VITE_API_URL || '/v1') {
		this.baseURL = baseURL
	}

	private async request<T>(
		endpoint: string,
		options: FetchOptions = {},
	): Promise<T> {
		const { params, ...fetchOptions } = options

		let url = `${this.baseURL}${endpoint}`
		
		if (params) {
			const searchParams = new URLSearchParams(
				Object.entries(params).map(([key, value]) => [key, String(value)]),
			)
			url += `?${searchParams}`
		}

		const headers = new Headers(fetchOptions.headers)
		if (!headers.has('Content-Type') && fetchOptions.body) {
			headers.set('Content-Type', 'application/json')
		}

		const response = await fetch(url, {
			...fetchOptions,
			headers,
		})

		if (!response.ok) {
			const errorData = await response.json().catch(() => null)
			throw new APIError(
				errorData?.detail || response.statusText,
				response.status,
				errorData,
			)
		}

		const contentType = response.headers.get('Content-Type')
		if (!contentType?.includes('application/json')) {
			return null as T
		}

		return response.json()
	}

	async get<T>(endpoint: string, options?: FetchOptions): Promise<T> {
		return this.request<T>(endpoint, { ...options, method: 'GET' })
	}

	async post<T>(endpoint: string, data?: unknown, options?: FetchOptions): Promise<T> {
		return this.request<T>(endpoint, {
			...options,
			method: 'POST',
			body: data ? JSON.stringify(data) : undefined,
		})
	}

	async put<T>(endpoint: string, data?: unknown, options?: FetchOptions): Promise<T> {
		return this.request<T>(endpoint, {
			...options,
			method: 'PUT',
			body: data ? JSON.stringify(data) : undefined,
		})
	}

	async patch<T>(endpoint: string, data?: unknown, options?: FetchOptions): Promise<T> {
		return this.request<T>(endpoint, {
			...options,
			method: 'PATCH',
			body: data ? JSON.stringify(data) : undefined,
		})
	}

	async delete<T>(endpoint: string, options?: FetchOptions): Promise<T> {
		return this.request<T>(endpoint, { ...options, method: 'DELETE' })
	}
}

export const apiClient = new APIClient()
export { APIError }
export type { FetchOptions }


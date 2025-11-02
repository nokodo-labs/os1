// Auto-generated from OpenAPI schema - DO NOT EDIT
// Run: npm run generate:api-types
export interface paths {
	'/health': {
		get: {
			responses: {
				200: {
					content: {
						'application/json': {
							status: string
						}
					}
				}
			}
		}
	}
	'/users': {
		get: {
			parameters: {
				query?: {
					skip?: number
					limit?: number
				}
			}
			responses: {
				200: {
					content: {
						'application/json': Array<{
							id: number
							email: string
							username: string
							is_active: boolean
							is_superuser: boolean
							created_at: string
						}>
					}
				}
			}
		}
		post: {
			requestBody: {
				content: {
					'application/json': {
						email: string
						username: string
						password: string
						is_active?: boolean
						is_superuser?: boolean
					}
				}
			}
			responses: {
				201: {
					content: {
						'application/json': {
							id: number
							email: string
							username: string
							is_active: boolean
							is_superuser: boolean
							created_at: string
						}
					}
				}
			}
		}
	}
	'/users/{user_id}': {
		get: {
			parameters: {
				path: {
					user_id: number
				}
			}
			responses: {
				200: {
					content: {
						'application/json': {
							id: number
							email: string
							username: string
							is_active: boolean
							is_superuser: boolean
							created_at: string
						}
					}
				}
				404: {
					content: {
						'application/json': {
							detail: string
						}
					}
				}
			}
		}
	}
}

// Helper types for easy extraction
export type User = paths['/users']['post']['responses'][201]['content']['application/json']
export type UserCreate = paths['/users']['post']['requestBody']['content']['application/json']
export type HealthCheck = paths['/health']['get']['responses'][200]['content']['application/json']

import { OpenAPI } from '$lib/api/generated'
import { getAccessToken } from '$lib/auth/session'

export function configureApiAuth(): void {
	OpenAPI.TOKEN = async () => getAccessToken() ?? ''
}

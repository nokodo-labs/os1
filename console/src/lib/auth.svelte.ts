import { browser } from '$app/environment'
import { AuthService, UsersService, type User } from '$lib/api'

function parseJwt(token: string) {
	try {
		return JSON.parse(atob(token.split('.')[1]))
	} catch (e) {
		return null
	}
}

class AuthState {
	token = $state<string | null>(browser ? localStorage.getItem('access_token') : null)
	user = $state<User | null>(null)
	isAuthenticated = $derived(!!this.token)

	constructor() {
		if (this.token) {
			this.fetchUser()
		}
	}

	async login(email: string, password: string) {
		const data = await AuthService.loginAccessTokenAuthLoginAccessTokenPost({
			username: email,
			password: password,
			scope: '',
		})

		this.setToken(data.access_token)
		await this.fetchUser()
	}

	async fetchUser() {
		if (!this.token) return
		const decoded = parseJwt(this.token)
		if (!decoded || !decoded.sub) return

		const userId = String(decoded.sub)
		try {
			this.user = await UsersService.readUserUsersUserIdGet(userId)
		} catch (e) {
			console.error('Failed to fetch user', e)
			this.logout()
		}
	}

	async register(email: string, password: string) {
		await UsersService.createUserUsersPost({
			email,
			password,
			is_active: true,
			is_superuser: true, // First user should be superuser? Or let backend handle it?
			// The user said "CREATE a brand new user, since that will be the first thing to do when you first spin up the project!"
			// So making them superuser seems appropriate for the console.
		})
	}

	logout() {
		this.token = null
		this.user = null
		if (browser) {
			localStorage.removeItem('access_token')
		}
	}

	private setToken(token: string) {
		this.token = token
		if (browser) {
			localStorage.setItem('access_token', token)
		}
	}
}

export const auth = new AuthState()

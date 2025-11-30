import { api, type User } from "$lib/api";

function parseJwt(token: string) {
	try {
		return JSON.parse(atob(token.split(".")[1]));
	} catch (e) {
		return null;
	}
}

class AuthState {
	token = $state<string | null>(localStorage.getItem("access_token"));
	user = $state<User | null>(null);
	isAuthenticated = $derived(!!this.token);

	constructor() {
		if (this.token) {
			this.fetchUser();
		}
	}

	async login(email: string, password: string) {
		const data = await api.login({
			username: email,
			password: password,
			scope: "",
		});

		this.setToken(data.access_token);
		await this.fetchUser();
	}

	async fetchUser() {
		if (!this.token) return;
		const decoded = parseJwt(this.token);
		if (!decoded || !decoded.sub) return;

		const userId = parseInt(decoded.sub);
		try {
			this.user = await api.getUser(userId);
		} catch (e) {
			console.error("Failed to fetch user", e);
			this.logout();
		}
	}

	async register(email: string, username: string, password: string) {
		await api.register({
			email,
			username,
			password,
			is_active: true,
			is_superuser: true, // First user should be superuser? Or let backend handle it?
			// The user said "CREATE a brand new user, since that will be the first thing to do when you first spin up the project!"
			// So making them superuser seems appropriate for the console.
		});
	}

	logout() {
		this.token = null;
		this.user = null;
		localStorage.removeItem("access_token");
	}

	private setToken(token: string) {
		this.token = token;
		localStorage.setItem("access_token", token);
	}
}

export const auth = new AuthState();

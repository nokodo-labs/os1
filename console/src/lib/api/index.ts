import { apiClient, APIError } from "./client";
import type { components } from "./types";

type User = components["schemas"]["User"];
type UserCreate = components["schemas"]["UserCreate"];
type Token = components["schemas"]["Token"];
type Body_login_access_token_auth_login_access_token_post =
	components["schemas"]["Body_login_access_token_auth_login_access_token_post"];

// Temporary types until regeneration
export interface Provider {
	id: string;
	name: string;
	adapter_type: string;
	provider_type: "local" | "external";
	base_url?: string;
	model_prefix?: string;
	additional_headers?: Record<string, string>;
	status: "enabled" | "disabled";
	is_autofetch_enabled: boolean;
	created_at: string;
	updated_at: string;
}

export interface ProviderCreate {
	name: string;
	adapter_type: string;
	provider_type?: "local" | "external";
	base_url?: string;
	api_key?: string;
	encrypted_api_key?: string;
	model_prefix?: string;
	additional_headers?: Record<string, string>;
	is_autofetch_enabled?: boolean;
}

export const api = {
	async login(
		data: Body_login_access_token_auth_login_access_token_post
	): Promise<Token> {
		const body = new URLSearchParams();
		body.append("username", data.username);
		body.append("password", data.password);
		if (data.grant_type) body.append("grant_type", data.grant_type);
		if (data.scope) body.append("scope", data.scope);
		if (data.client_id) body.append("client_id", data.client_id);
		if (data.client_secret)
			body.append("client_secret", data.client_secret);

		return apiClient.postForm<Token>("/auth/login/access-token", body);
	},

	async register(data: UserCreate): Promise<User> {
		return apiClient.post<User>("/users", data);
	},

	async getUser(userId: number): Promise<User> {
		return apiClient.get<User>(`/users/${userId}`);
	},

	async getSystemStatus(): Promise<{ initialized: boolean }> {
		return apiClient.get<{ initialized: boolean }>("/system/status");
	},

	async getProviders(): Promise<Provider[]> {
		return apiClient.get<Provider[]>("/providers");
	},

	async createProvider(data: ProviderCreate): Promise<Provider> {
		return apiClient.post<Provider>("/providers", data);
	},

	async updateProvider(
		id: string,
		data: Partial<ProviderCreate>
	): Promise<Provider> {
		return apiClient.patch<Provider>(`/providers/${id}`, data);
	},
};

export { apiClient, APIError };
export type { Token, User, UserCreate };

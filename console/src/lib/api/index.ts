import { apiClient, APIError } from "./client";
import type { components } from "./types";

type User = components["schemas"]["User"];
type UserCreate = components["schemas"]["UserCreate"];
type Token = components["schemas"]["Token"];
type Body_login_access_token_auth_login_access_token_post =
	components["schemas"]["Body_login_access_token_auth_login_access_token_post"];

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
};

export { apiClient, APIError };
export type { Token, User, UserCreate };

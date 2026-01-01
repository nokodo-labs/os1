/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_login_access_token_auth_login_access_token_post } from '../models/Body_login_access_token_auth_login_access_token_post';
import type { Token } from '../models/Token';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AuthService {
    /**
     * Login Access Token
     * OAuth2 compatible token login, get an access token for future requests.
     * @param formData
     * @returns Token Successful Response
     * @throws ApiError
     */
    public static loginAccessTokenAuthLoginAccessTokenPost(
        formData: Body_login_access_token_auth_login_access_token_post,
    ): CancelablePromise<Token> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/auth/login/access-token',
            formData: formData,
            mediaType: 'application/x-www-form-urlencoded',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Refresh Access Token
     * Exchange refresh token for new access token (sliding refresh).
     * @param refreshToken
     * @returns Token Successful Response
     * @throws ApiError
     */
    public static refreshAccessTokenAuthRefreshPost(
        refreshToken?: (string | null),
    ): CancelablePromise<Token> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/auth/refresh',
            cookies: {
                'refresh_token': refreshToken,
            },
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Logout
     * Clear refresh token cookie to log out.
     * @returns void
     * @throws ApiError
     */
    public static logoutAuthLogoutPost(): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/auth/logout',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
}

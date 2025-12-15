/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Provider } from '../models/Provider';
import type { ProviderCreate } from '../models/ProviderCreate';
import type { ProviderUpdate } from '../models/ProviderUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ProvidersService {
    /**
     * List Providers
     * List configured providers.
     * @returns Provider Successful Response
     * @throws ApiError
     */
    public static listProvidersProvidersGet(): CancelablePromise<Array<Provider>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/providers',
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
     * Create Provider
     * Register a provider.
     * @param requestBody
     * @returns Provider Successful Response
     * @throws ApiError
     */
    public static createProviderProvidersPost(
        requestBody: ProviderCreate,
    ): CancelablePromise<Provider> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/providers',
            body: requestBody,
            mediaType: 'application/json',
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
     * Get Provider
     * Fetch a provider.
     * @param providerId
     * @returns Provider Successful Response
     * @throws ApiError
     */
    public static getProviderProvidersProviderIdGet(
        providerId: string,
    ): CancelablePromise<Provider> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/providers/{provider_id}',
            path: {
                'provider_id': providerId,
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
     * Update Provider
     * Update provider fields.
     * @param providerId
     * @param requestBody
     * @returns Provider Successful Response
     * @throws ApiError
     */
    public static updateProviderProvidersProviderIdPatch(
        providerId: string,
        requestBody: ProviderUpdate,
    ): CancelablePromise<Provider> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/providers/{provider_id}',
            path: {
                'provider_id': providerId,
            },
            body: requestBody,
            mediaType: 'application/json',
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

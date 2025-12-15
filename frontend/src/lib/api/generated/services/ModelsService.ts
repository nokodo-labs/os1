/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Model } from '../models/Model';
import type { ModelCreate } from '../models/ModelCreate';
import type { ModelUpdate } from '../models/ModelUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ModelsService {
    /**
     * Create Model
     * Register a model for a provider.
     * @param requestBody
     * @returns Model Successful Response
     * @throws ApiError
     */
    public static createModelModelsPost(
        requestBody: ModelCreate,
    ): CancelablePromise<Model> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/models',
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
     * List Models
     * List models with optional provider filter.
     * @param providerId
     * @returns Model Successful Response
     * @throws ApiError
     */
    public static listModelsModelsGet(
        providerId?: (string | null),
    ): CancelablePromise<Array<Model>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/models',
            query: {
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
     * Get Model
     * Fetch a single model.
     * @param modelId
     * @returns Model Successful Response
     * @throws ApiError
     */
    public static getModelModelsModelIdGet(
        modelId: string,
    ): CancelablePromise<Model> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/models/{model_id}',
            path: {
                'model_id': modelId,
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
     * Update Model
     * Update a model.
     * @param modelId
     * @param requestBody
     * @returns Model Successful Response
     * @throws ApiError
     */
    public static updateModelModelsModelIdPatch(
        modelId: string,
        requestBody: ModelUpdate,
    ): CancelablePromise<Model> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/models/{model_id}',
            path: {
                'model_id': modelId,
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
    /**
     * Delete Model
     * Delete a model.
     * @param modelId
     * @returns void
     * @throws ApiError
     */
    public static deleteModelModelsModelIdDelete(
        modelId: string,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/models/{model_id}',
            path: {
                'model_id': modelId,
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
}

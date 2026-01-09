/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Prompt } from '../models/Prompt';
import type { PromptCreate } from '../models/PromptCreate';
import type { PromptUpdate } from '../models/PromptUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class PromptsService {
    /**
     * Create Prompt
     * Create a prompt.
     * @param requestBody
     * @returns Prompt Successful Response
     * @throws ApiError
     */
    public static createPromptPromptsPost(
        requestBody: PromptCreate,
    ): CancelablePromise<Prompt> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/prompts',
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
     * List Prompts
     * List prompts.
     * @param skip
     * @param limit
     * @param sortBy
     * @param sortDir
     * @returns Prompt Successful Response
     * @throws ApiError
     */
    public static listPromptsPromptsGet(
        skip?: number,
        limit: number = 50,
        sortBy: 'command' | 'created_at' | 'updated_at' = 'command',
        sortDir: 'asc' | 'desc' = 'asc',
    ): CancelablePromise<Array<Prompt>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/prompts',
            query: {
                'skip': skip,
                'limit': limit,
                'sort_by': sortBy,
                'sort_dir': sortDir,
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
     * Get Prompt
     * Fetch a prompt.
     * @param promptId
     * @returns Prompt Successful Response
     * @throws ApiError
     */
    public static getPromptPromptsPromptIdGet(
        promptId: string,
    ): CancelablePromise<Prompt> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/prompts/{prompt_id}',
            path: {
                'prompt_id': promptId,
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
     * Update Prompt
     * Update a prompt.
     * @param promptId
     * @param requestBody
     * @returns Prompt Successful Response
     * @throws ApiError
     */
    public static updatePromptPromptsPromptIdPatch(
        promptId: string,
        requestBody: PromptUpdate,
    ): CancelablePromise<Prompt> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/prompts/{prompt_id}',
            path: {
                'prompt_id': promptId,
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
     * Delete Prompt
     * Delete a prompt.
     * @param promptId
     * @returns void
     * @throws ApiError
     */
    public static deletePromptPromptsPromptIdDelete(
        promptId: string,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/prompts/{prompt_id}',
            path: {
                'prompt_id': promptId,
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

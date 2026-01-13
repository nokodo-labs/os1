/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CommonSortBy } from '../models/CommonSortBy';
import type { Memory } from '../models/Memory';
import type { MemoryCreate } from '../models/MemoryCreate';
import type { MemoryUpdate } from '../models/MemoryUpdate';
import type { SortDir } from '../models/SortDir';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MemoriesService {
    /**
     * Create Memory
     * Capture a new memory.
     * @param requestBody
     * @param embeddingModelId
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static createMemoryMemoriesPost(
        requestBody: MemoryCreate,
        embeddingModelId?: (string | null),
    ): CancelablePromise<Memory> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/memories',
            query: {
                'embedding_model_id': embeddingModelId,
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
     * List Memories
     * List memories for a user.
     * @param userId
     * @param skip
     * @param limit
     * @param sortBy
     * @param sortDir
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static listMemoriesMemoriesGet(
        userId: string,
        skip?: number,
        limit: number = 50,
        sortBy?: (CommonSortBy | 'category' | 'last_accessed_at' | 'confidence'),
        sortDir: SortDir = 'desc',
    ): CancelablePromise<Array<Memory>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/memories',
            query: {
                'user_id': userId,
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
     * Get Memory
     * Fetch a single memory.
     * @param memoryId
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static getMemoryMemoriesMemoryIdGet(
        memoryId: string,
    ): CancelablePromise<Memory> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/memories/{memory_id}',
            path: {
                'memory_id': memoryId,
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
     * Update Memory
     * Update a memory.
     * @param memoryId
     * @param requestBody
     * @param embeddingModelId
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static updateMemoryMemoriesMemoryIdPut(
        memoryId: string,
        requestBody: MemoryUpdate,
        embeddingModelId?: (string | null),
    ): CancelablePromise<Memory> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/memories/{memory_id}',
            path: {
                'memory_id': memoryId,
            },
            query: {
                'embedding_model_id': embeddingModelId,
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
     * Delete Memory
     * Delete a memory.
     * @param memoryId
     * @returns void
     * @throws ApiError
     */
    public static deleteMemoryMemoriesMemoryIdDelete(
        memoryId: string,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/memories/{memory_id}',
            path: {
                'memory_id': memoryId,
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

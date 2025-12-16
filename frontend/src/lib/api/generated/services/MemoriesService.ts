/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Memory } from '../models/Memory';
import type { MemoryCreate } from '../models/MemoryCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class MemoriesService {
    /**
     * Create Memory
     * Capture a new memory.
     * @param requestBody
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static createMemoryMemoriesPost(
        requestBody: MemoryCreate,
    ): CancelablePromise<Memory> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/memories',
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
     * @returns Memory Successful Response
     * @throws ApiError
     */
    public static listMemoriesMemoriesGet(
        userId: string,
        skip?: number,
        limit: number = 50,
    ): CancelablePromise<Array<Memory>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/memories',
            query: {
                'user_id': userId,
                'skip': skip,
                'limit': limit,
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
}

/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessControlEntry } from '../models/AccessControlEntry';
import type { AccessControlEntryCreate } from '../models/AccessControlEntryCreate';
import type { Message } from '../models/Message';
import type { MessageCreate } from '../models/MessageCreate';
import type { Thread } from '../models/Thread';
import type { ThreadCreate } from '../models/ThreadCreate';
import type { ThreadUpdate } from '../models/ThreadUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ThreadsService {
    /**
     * Create Thread
     * Create a new thread.
     * @param requestBody
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static createThreadThreadsPost(
        requestBody: ThreadCreate,
    ): CancelablePromise<Thread> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/threads',
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
     * List Threads
     * List threads optionally filtered by owner.
     * @param ownerId
     * @param skip
     * @param limit
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static listThreadsThreadsGet(
        ownerId?: (number | null),
        skip?: number,
        limit: number = 20,
    ): CancelablePromise<Array<Thread>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads',
            query: {
                'owner_id': ownerId,
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
     * Get Thread
     * Fetch a single thread with messages.
     * @param threadId
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static getThreadThreadsThreadIdGet(
        threadId: string,
    ): CancelablePromise<Thread> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}',
            path: {
                'thread_id': threadId,
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
     * Update Thread
     * Update thread metadata.
     * @param threadId
     * @param requestBody
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static updateThreadThreadsThreadIdPatch(
        threadId: string,
        requestBody: ThreadUpdate,
    ): CancelablePromise<Thread> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/threads/{thread_id}',
            path: {
                'thread_id': threadId,
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
     * List Messages
     * List messages within a thread.
     * @param threadId
     * @param skip
     * @param limit
     * @returns Message Successful Response
     * @throws ApiError
     */
    public static listMessagesThreadsThreadIdMessagesGet(
        threadId: string,
        skip?: number,
        limit: number = 100,
    ): CancelablePromise<Array<Message>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}/messages',
            path: {
                'thread_id': threadId,
            },
            query: {
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
     * Create Message
     * Append a message to a thread.
     * @param threadId
     * @param requestBody
     * @returns Message Successful Response
     * @throws ApiError
     */
    public static createMessageThreadsThreadIdMessagesPost(
        threadId: string,
        requestBody: MessageCreate,
    ): CancelablePromise<Message> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/threads/{thread_id}/messages',
            path: {
                'thread_id': threadId,
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
     * List Thread Acl
     * List acl entries for a thread.
     * @param threadId
     * @returns AccessControlEntry Successful Response
     * @throws ApiError
     */
    public static listThreadAclThreadsThreadIdAclGet(
        threadId: string,
    ): CancelablePromise<Array<AccessControlEntry>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}/acl',
            path: {
                'thread_id': threadId,
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
     * Set Thread Acl
     * Replace acl entries for a thread.
     * @param threadId
     * @param requestBody
     * @returns AccessControlEntry Successful Response
     * @throws ApiError
     */
    public static setThreadAclThreadsThreadIdAclPut(
        threadId: string,
        requestBody: Array<AccessControlEntryCreate>,
    ): CancelablePromise<Array<AccessControlEntry>> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/threads/{thread_id}/acl',
            path: {
                'thread_id': threadId,
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

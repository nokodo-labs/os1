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
import type { ThreadRunRequest } from '../models/ThreadRunRequest';
import type { ThreadRunResponse } from '../models/ThreadRunResponse';
import type { ThreadSwitchRequest } from '../models/ThreadSwitchRequest';
import type { ThreadSwitchResponse } from '../models/ThreadSwitchResponse';
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
     * @param includeHidden
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static listThreadsThreadsGet(
        ownerId?: (string | null),
        skip?: number,
        limit: number = 20,
        includeHidden: boolean = false,
    ): CancelablePromise<Array<Thread>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads',
            query: {
                'owner_id': ownerId,
                'skip': skip,
                'limit': limit,
                'include_hidden': includeHidden,
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
     * @param includeHidden
     * @returns Thread Successful Response
     * @throws ApiError
     */
    public static getThreadThreadsThreadIdGet(
        threadId: string,
        includeHidden: boolean = false,
    ): CancelablePromise<Thread> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}',
            path: {
                'thread_id': threadId,
            },
            query: {
                'include_hidden': includeHidden,
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
     * Delete Thread
     * Delete a thread.
     * @param threadId
     * @returns void
     * @throws ApiError
     */
    public static deleteThreadThreadsThreadIdDelete(
        threadId: string,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
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
     * List Messages
     * List messages within a thread.
     * @param threadId
     * @param skip
     * @param limit
     * @param includeHidden
     * @returns Message Successful Response
     * @throws ApiError
     */
    public static listMessagesThreadsThreadIdMessagesGet(
        threadId: string,
        skip?: number,
        limit: number = 100,
        includeHidden: boolean = false,
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
                'include_hidden': includeHidden,
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
     * Get Current Branch
     * Return the current root→leaf branch for this thread.
     * @param threadId
     * @param includeHidden
     * @returns Message Successful Response
     * @throws ApiError
     */
    public static getCurrentBranchThreadsThreadIdBranchGet(
        threadId: string,
        includeHidden: boolean = false,
    ): CancelablePromise<Array<Message>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}/branch',
            path: {
                'thread_id': threadId,
            },
            query: {
                'include_hidden': includeHidden,
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
     * Get Message Tree
     * Return all messages for this thread as a flat list.
     * @param threadId
     * @param includeHidden
     * @returns Message Successful Response
     * @throws ApiError
     */
    public static getMessageTreeThreadsThreadIdTreeGet(
        threadId: string,
        includeHidden: boolean = false,
    ): CancelablePromise<Array<Message>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/threads/{thread_id}/tree',
            path: {
                'thread_id': threadId,
            },
            query: {
                'include_hidden': includeHidden,
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
     * Run Thread
     * run a thread with an agent and persist all messages produced.
     * @param threadId
     * @param requestBody
     * @returns ThreadRunResponse Successful Response
     * @throws ApiError
     */
    public static runThreadThreadsThreadIdRunPost(
        threadId: string,
        requestBody: ThreadRunRequest,
    ): CancelablePromise<ThreadRunResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/threads/{thread_id}/run',
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
     * Run Thread Stream
     * stream a thread run via sse events.
     * @param threadId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static runThreadStreamThreadsThreadIdRunStreamPost(
        threadId: string,
        requestBody: ThreadRunRequest,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/threads/{thread_id}/run/stream',
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
     * Switch Branch
     * Switch the active branch to the subtree rooted at message_id.
     * @param threadId
     * @param requestBody
     * @returns ThreadSwitchResponse Successful Response
     * @throws ApiError
     */
    public static switchBranchThreadsThreadIdSwitchPost(
        threadId: string,
        requestBody: ThreadSwitchRequest,
    ): CancelablePromise<ThreadSwitchResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/threads/{thread_id}/switch',
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

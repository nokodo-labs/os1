/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Event } from '../models/Event';
import type { EventCreate } from '../models/EventCreate';
import type { EventScope } from '../models/EventScope';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class EventsService {
    /**
     * Emit Event
     * Persist and broadcast an event.
     * @param requestBody
     * @returns Event Successful Response
     * @throws ApiError
     */
    public static emitEventEventsPost(
        requestBody: EventCreate,
    ): CancelablePromise<Event> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/events',
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
     * List Events
     * Query events with flexible filters.
     * @param scope
     * @param threadId
     * @param taskId
     * @param userId
     * @param since
     * @returns Event Successful Response
     * @throws ApiError
     */
    public static listEventsEventsGet(
        scope?: (EventScope | null),
        threadId?: (string | null),
        taskId?: (string | null),
        userId?: (number | null),
        since?: (string | null),
    ): CancelablePromise<Array<Event>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/events',
            query: {
                'scope': scope,
                'thread_id': threadId,
                'task_id': taskId,
                'user_id': userId,
                'since': since,
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

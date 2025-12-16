/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Task } from '../models/Task';
import type { TaskCreate } from '../models/TaskCreate';
import type { TaskStatus } from '../models/TaskStatus';
import type { TaskUpdate } from '../models/TaskUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class TasksService {
    /**
     * Create Task
     * Create a new task.
     * @param requestBody
     * @returns Task Successful Response
     * @throws ApiError
     */
    public static createTaskTasksPost(
        requestBody: TaskCreate,
    ): CancelablePromise<Task> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/tasks',
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
     * List Tasks
     * List tasks with optional filters.
     * @param userId
     * @param statusFilter
     * @param skip
     * @param limit
     * @returns Task Successful Response
     * @throws ApiError
     */
    public static listTasksTasksGet(
        userId?: (string | null),
        statusFilter?: (TaskStatus | null),
        skip?: number,
        limit: number = 50,
    ): CancelablePromise<Array<Task>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/tasks',
            query: {
                'user_id': userId,
                'status_filter': statusFilter,
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
     * Update Task
     * Update mutable task fields.
     * @param taskId
     * @param requestBody
     * @returns Task Successful Response
     * @throws ApiError
     */
    public static updateTaskTasksTaskIdPatch(
        taskId: string,
        requestBody: TaskUpdate,
    ): CancelablePromise<Task> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/tasks/{task_id}',
            path: {
                'task_id': taskId,
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

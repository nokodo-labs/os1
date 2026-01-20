/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CommonSortBy } from '../models/CommonSortBy';
import type { SortDir } from '../models/SortDir';
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
     * create a new task.
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
     * list tasks with optional filters.
     * @param userId
     * @param statusFilter
     * @param skip
     * @param limit
     * @param sortBy
     * @param sortDir
     * @returns Task Successful Response
     * @throws ApiError
     */
    public static listTasksTasksGet(
        userId?: (string | null),
        statusFilter?: (TaskStatus | null),
        skip?: number,
        limit: number = 50,
        sortBy?: (CommonSortBy | 'status' | 'task_type' | 'stage' | 'last_event_at'),
        sortDir: SortDir = 'desc',
    ): CancelablePromise<Array<Task>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/tasks',
            query: {
                'user_id': userId,
                'status_filter': statusFilter,
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
     * Update Task
     * update mutable task fields.
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

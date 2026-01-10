/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { TaskStatus } from './TaskStatus';
import type { TaskType } from './TaskType';
/**
 * Payload to start a task.
 */
export type TaskCreate = {
    metadata_?: ApiJSONObject;
    task_type?: TaskType;
    status?: TaskStatus;
    progress?: (number | null);
    stage?: (string | null);
    result?: (Record<string, any> | null);
    user_id: string;
    spawned_thread_id?: (string | null);
};


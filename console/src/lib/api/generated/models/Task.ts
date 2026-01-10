/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { TaskStatus } from './TaskStatus';
import type { TaskType } from './TaskType';
/**
 * Response model.
 */
export type Task = {
    metadata_?: ApiJSONObject;
    task_type?: TaskType;
    status?: TaskStatus;
    progress?: (number | null);
    stage?: (string | null);
    result?: (Record<string, any> | null);
    id: string;
    user_id: string;
    spawned_thread_id?: (string | null);
    started_at?: (string | null);
    completed_at?: (string | null);
    cancelled_at?: (string | null);
    last_event_at?: (string | null);
    created_at: string;
    updated_at: string;
};


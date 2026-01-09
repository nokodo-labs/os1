/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
import type { TaskStatus } from './TaskStatus';
/**
 * Mutable task fields for PATCH operations.
 */
export type TaskUpdate = {
    metadata_?: JSONObject_Input;
    status?: (TaskStatus | null);
    progress?: (number | null);
    stage?: (string | null);
    result?: (Record<string, any> | null);
};


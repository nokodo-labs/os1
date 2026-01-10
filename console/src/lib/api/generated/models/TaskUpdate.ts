/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { TaskStatus } from './TaskStatus';
/**
 * Mutable task fields for PATCH operations.
 */
export type TaskUpdate = {
    metadata_?: ApiJSONObject;
    status?: (TaskStatus | null);
    progress?: (number | null);
    stage?: (string | null);
    result?: (Record<string, any> | null);
};


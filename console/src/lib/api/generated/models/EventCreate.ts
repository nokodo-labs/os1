/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { EventScope } from './EventScope';
/**
 * Payload to emit a new event.
 */
export type EventCreate = {
    metadata_?: ApiJSONObject;
    scope?: EventScope;
    scope_id?: (string | null);
    type: string;
    data?: Record<string, any>;
    expires_at?: (string | null);
    version?: number;
    user_id?: (string | null);
    thread_id?: (string | null);
    message_id?: (string | null);
    task_id?: (string | null);
};


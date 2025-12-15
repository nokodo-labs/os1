/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EventScope } from './EventScope';
/**
 * Event response.
 */
export type Event = {
    metadata_?: Record<string, any>;
    scope?: EventScope;
    scope_id?: (string | null);
    type: string;
    data?: Record<string, any>;
    expires_at?: (string | null);
    version?: number;
    user_id?: (number | null);
    thread_id?: (string | null);
    message_id?: (string | null);
    task_id?: (string | null);
    id: string;
    created_at: string;
    updated_at: string;
};


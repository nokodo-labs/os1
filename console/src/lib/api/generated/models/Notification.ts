/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Event } from './Event';
/**
 * Response schema.
 */
export type Notification = {
    user_id: number;
    event_id: string;
    dismissed?: boolean;
    id: string;
    read_at?: (string | null);
    created_at: string;
    updated_at: string;
    event?: (Event | null);
};


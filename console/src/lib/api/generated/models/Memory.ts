/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Output } from './JSONObject_Output';
import type { User } from './User';
/**
 * Response schema.
 */
export type Memory = {
    metadata_?: JSONObject_Output;
    content: string;
    source_message_id?: (string | null);
    confidence?: (number | null);
    category?: (string | null);
    id: string;
    user_id: string;
    embedding?: (Blob | null);
    last_accessed_at?: (string | null);
    created_at: string;
    updated_at: string;
    owner?: (User | null);
};


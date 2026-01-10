/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * Payload to capture a memory.
 */
export type MemoryCreate = {
    metadata_?: ApiJSONObject;
    content: string;
    source_message_id?: (string | null);
    confidence?: (number | null);
    category?: (string | null);
    user_id: string;
};


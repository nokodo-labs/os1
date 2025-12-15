/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload to capture a memory.
 */
export type MemoryCreate = {
    metadata_?: Record<string, any>;
    content: string;
    source_message_id?: (string | null);
    confidence?: (number | null);
    category?: (string | null);
    user_id: number;
};


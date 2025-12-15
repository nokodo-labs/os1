/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Project schema.
 */
export type Project = {
    created_at: string;
    updated_at: string;
    metadata_?: Record<string, any>;
    name: string;
    description?: (string | null);
    id: string;
    owner_id: number;
    thread_ids?: Array<string>;
};


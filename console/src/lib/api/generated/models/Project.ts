/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * Project schema.
 */
export type Project = {
    created_at: string;
    updated_at: string;
    metadata_?: ApiJSONObject;
    name: string;
    description?: (string | null);
    id: string;
    owner_id: string;
    thread_ids?: Array<string>;
};


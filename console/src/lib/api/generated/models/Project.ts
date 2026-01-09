/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Output } from './JSONObject_Output';
/**
 * Project schema.
 */
export type Project = {
    created_at: string;
    updated_at: string;
    metadata_?: JSONObject_Output;
    name: string;
    description?: (string | null);
    id: string;
    owner_id: string;
    thread_ids?: Array<string>;
};


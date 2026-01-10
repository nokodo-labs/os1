/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * Payload for creating a thread.
 */
export type ThreadCreate = {
    metadata_?: ApiJSONObject;
    title?: (string | null);
    tags?: Array<string>;
    is_archived?: boolean;
    is_temporary?: boolean;
    project_ids?: Array<string>;
    owner_id: string;
};


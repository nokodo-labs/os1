/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
/**
 * Payload for creating a thread.
 */
export type ThreadCreate = {
    metadata_?: JSONObject_Input;
    title?: (string | null);
    tags?: Array<string>;
    is_archived?: boolean;
    is_temporary?: boolean;
    project_ids?: Array<string>;
    owner_id: string;
};


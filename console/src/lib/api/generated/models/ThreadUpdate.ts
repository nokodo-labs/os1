/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
/**
 * Payload for updating a thread.
 */
export type ThreadUpdate = {
    metadata_?: JSONObject_Input;
    title?: (string | null);
    tags?: (Array<string> | null);
    is_archived?: (boolean | null);
    is_temporary?: (boolean | null);
    project_ids?: (Array<string> | null);
    owner_id?: (string | null);
};


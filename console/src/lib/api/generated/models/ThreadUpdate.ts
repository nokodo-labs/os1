/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload for updating a thread.
 */
export type ThreadUpdate = {
    metadata_?: Record<string, any>;
    title?: (string | null);
    tags?: (Array<string> | null);
    is_archived?: (boolean | null);
    project_ids?: (Array<string> | null);
    owner_id?: (number | null);
};


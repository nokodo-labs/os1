/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload for creating a thread.
 */
export type ThreadCreate = {
    metadata_?: Record<string, any>;
    title?: (string | null);
    tags?: Array<string>;
    is_archived?: boolean;
    project_ids?: Array<string>;
    owner_id: string;
};


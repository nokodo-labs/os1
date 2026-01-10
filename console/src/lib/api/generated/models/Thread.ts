/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { Project } from './Project';
import type { User } from './User';
/**
 * Detailed response schema.
 */
export type Thread = {
    metadata_?: ApiJSONObject;
    title?: (string | null);
    tags?: Array<string>;
    is_archived?: boolean;
    is_temporary?: boolean;
    project_ids?: Array<string>;
    id: string;
    owner_id: string;
    current_message_id?: (string | null);
    last_activity_at: string;
    created_at: string;
    updated_at: string;
    deleted_at?: (string | null);
    owner?: (User | null);
    projects?: Array<Project>;
};


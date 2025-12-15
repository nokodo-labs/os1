/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Message } from './Message';
import type { Project } from './Project';
import type { User } from './User';
/**
 * Detailed response schema.
 */
export type Thread = {
    metadata_?: Record<string, any>;
    title?: (string | null);
    tags?: Array<string>;
    is_archived?: boolean;
    project_ids?: Array<string>;
    id: string;
    owner_id: number;
    last_activity_at: string;
    created_at: string;
    updated_at: string;
    owner?: (User | null);
    messages?: Array<Message>;
    projects?: Array<Project>;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessRole } from './AccessRole';
/**
 * response schema for an ace.
 */
export type AccessControlEntry = {
    created_at: string;
    updated_at: string;
    metadata_?: Record<string, any>;
    id: string;
    thread_id?: (string | null);
    project_id?: (string | null);
    user_id?: (number | null);
    group_id?: (string | null);
    agent_id?: (string | null);
    role: AccessRole;
};


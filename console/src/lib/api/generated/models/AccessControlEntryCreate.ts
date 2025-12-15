/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessRole } from './AccessRole';
/**
 * payload for setting acl entries on a resource.
 */
export type AccessControlEntryCreate = {
    metadata_?: Record<string, any>;
    user_id?: (number | null);
    group_id?: (string | null);
    agent_id?: (string | null);
    role?: AccessRole;
};


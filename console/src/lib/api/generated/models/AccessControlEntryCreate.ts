/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessRole } from './AccessRole';
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * payload for setting acl entries on a resource.
 */
export type AccessControlEntryCreate = {
    metadata_?: ApiJSONObject;
    user_id?: (string | null);
    group_id?: (string | null);
    agent_id?: (string | null);
    role?: AccessRole;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessRole } from './AccessRole';
import type { JSONObject_Input } from './JSONObject_Input';
/**
 * payload for setting acl entries on a resource.
 */
export type AccessControlEntryCreate = {
    metadata_?: JSONObject_Input;
    user_id?: (string | null);
    group_id?: (string | null);
    agent_id?: (string | null);
    role?: AccessRole;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * schema for updating a user.
 */
export type UserUpdate = {
    email?: (string | null);
    password?: (string | null);
    is_active?: (boolean | null);
    display_name?: (string | null);
    avatar_url?: (string | null);
    preferences?: (Record<string, any> | null);
    integration_tokens?: (Record<string, any> | null);
    usage_quotas?: (Record<string, any> | null);
};


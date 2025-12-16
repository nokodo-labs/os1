/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for user response.
 */
export type User = {
    email: string;
    display_name?: (string | null);
    avatar_url?: (string | null);
    is_active?: boolean;
    is_superuser?: boolean;
    preferences?: Record<string, any>;
    integration_tokens?: Record<string, any>;
    usage_quotas?: Record<string, any>;
    id: string;
    role_id?: (string | null);
    created_at: string;
    updated_at: string;
};


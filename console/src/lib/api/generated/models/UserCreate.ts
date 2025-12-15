/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Schema for creating a user.
 */
export type UserCreate = {
    email: string;
    display_name?: (string | null);
    avatar_url?: (string | null);
    is_active?: boolean;
    is_superuser?: boolean;
    preferences?: Record<string, any>;
    integration_tokens?: Record<string, any>;
    usage_quotas?: Record<string, any>;
    password: string;
};


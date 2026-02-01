/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * schema for creating a user.
 *
 * note: is_active and is_superuser are optional.
 * the server decides final values:
 * - bootstrap (first user): may be superuser only if explicitly requested
 * - unauthenticated: regular user only (is_active=True, is_superuser=False)
 * - authenticated superuser: can set privileges
 */
export type UserCreate = {
    email: string;
    password: string;
    display_name?: (string | null);
    is_active?: (boolean | null);
    is_superuser?: (boolean | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SecuritySettingsPatch = {
    /**
     * access token expire minutes
     */
    access_token_expire_minutes?: (number | null);
    /**
     * refresh token expire days
     */
    refresh_token_expire_days?: (number | null);
    /**
     * set secure cookies
     */
    auth_cookie_secure?: (boolean | null);
    /**
     * session timeout
     */
    session_timeout_minutes?: (number | null);
    /**
     * require email verification
     */
    require_email_verification?: (boolean | null);
    /**
     * allowed domains
     */
    allowed_email_domains?: (Array<string> | null);
};


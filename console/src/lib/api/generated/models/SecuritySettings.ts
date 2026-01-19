/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SecuritySettings = {
    /**
     * application secret key (env-only)
     */
    secret_key?: string;
    /**
     * jwt algorithm
     */
    jwt_algorithm?: string;
    /**
     * access token expire minutes
     */
    access_token_expire_minutes?: number;
    /**
     * refresh token expire days
     */
    refresh_token_expire_days?: number;
    /**
     * set secure cookies
     */
    auth_cookie_secure?: boolean;
    /**
     * session timeout
     */
    session_timeout_minutes?: number;
    /**
     * require email verification
     */
    require_email_verification?: boolean;
    /**
     * allowed domains
     */
    allowed_email_domains?: Array<string>;
    /**
     * enable oauth (env-only)
     */
    enable_oauth?: boolean;
    /**
     * cors origins (env-only)
     */
    cors_origins?: Array<string>;
};


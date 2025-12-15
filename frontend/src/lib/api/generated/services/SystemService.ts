/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { RuntimeConfigOut } from '../models/RuntimeConfigOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SystemService {
    /**
     * Get System Status
     * Check system initialization status.
     * @returns boolean Successful Response
     * @throws ApiError
     */
    public static getSystemStatusSystemStatusGet(): CancelablePromise<Record<string, boolean>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/system/status',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Get Runtime Config
     * Return runtime configuration values safe for clients.
     * @returns RuntimeConfigOut Successful Response
     * @throws ApiError
     */
    public static getRuntimeConfigSystemConfigGet(): CancelablePromise<RuntimeConfigOut> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/system/config',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
}

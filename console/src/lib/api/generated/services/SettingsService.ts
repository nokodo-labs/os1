/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SettingsResponse } from '../models/SettingsResponse';
import type { SettingsUpdateRequest } from '../models/SettingsUpdateRequest';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SettingsService {
    /**
     * Get Settings
     * get all settings.
     * @returns SettingsResponse Successful Response
     * @throws ApiError
     */
    public static getSettingsSettingsGet(): CancelablePromise<SettingsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/settings',
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
     * Update Settings
     * partial update settings (admin only).
     * @param requestBody
     * @returns SettingsResponse Successful Response
     * @throws ApiError
     */
    public static updateSettingsSettingsPatch(
        requestBody: SettingsUpdateRequest,
    ): CancelablePromise<SettingsResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/settings',
            body: requestBody,
            mediaType: 'application/json',
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

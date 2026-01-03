/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Plugin } from '../models/Plugin';
import type { PluginCreate } from '../models/PluginCreate';
import type { PluginInfo } from '../models/PluginInfo';
import type { PluginUpdate } from '../models/PluginUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class PluginsService {
    /**
     * List Available Plugins
     * list all available plugins (native and user-defined).
     *
     * native plugins are built into the system and cannot be modified.
     * use the plugin_type query parameter to filter by type.
     * @param pluginType
     * @returns PluginInfo Successful Response
     * @throws ApiError
     */
    public static listAvailablePluginsPluginsAvailableGet(
        pluginType?: ('tool' | 'filter' | 'hook' | null),
    ): CancelablePromise<Array<PluginInfo>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/plugins/available',
            query: {
                'plugin_type': pluginType,
            },
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
     * Get Available Plugin
     * get details about a specific available plugin (native or user-defined).
     * @param pluginId
     * @returns PluginInfo Successful Response
     * @throws ApiError
     */
    public static getAvailablePluginPluginsAvailablePluginIdGet(
        pluginId: string,
    ): CancelablePromise<PluginInfo> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/plugins/available/{plugin_id}',
            path: {
                'plugin_id': pluginId,
            },
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
     * List Plugins
     * List all plugin records.
     * @returns Plugin Successful Response
     * @throws ApiError
     */
    public static listPluginsPluginsGet(): CancelablePromise<Array<Plugin>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/plugins',
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
     * Create Plugin
     * Create a plugin record.
     * @param requestBody
     * @returns Plugin Successful Response
     * @throws ApiError
     */
    public static createPluginPluginsPost(
        requestBody: PluginCreate,
    ): CancelablePromise<Plugin> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/plugins',
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
    /**
     * Get Plugin
     * Fetch a plugin record by id.
     * @param pluginId
     * @returns Plugin Successful Response
     * @throws ApiError
     */
    public static getPluginPluginsPluginIdGet(
        pluginId: string,
    ): CancelablePromise<Plugin> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/plugins/{plugin_id}',
            path: {
                'plugin_id': pluginId,
            },
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
     * Update Plugin
     * Update plugin fields.
     * @param pluginId
     * @param requestBody
     * @returns Plugin Successful Response
     * @throws ApiError
     */
    public static updatePluginPluginsPluginIdPatch(
        pluginId: string,
        requestBody: PluginUpdate,
    ): CancelablePromise<Plugin> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/plugins/{plugin_id}',
            path: {
                'plugin_id': pluginId,
            },
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
    /**
     * Delete Plugin
     * Delete a plugin record.
     * @param pluginId
     * @returns void
     * @throws ApiError
     */
    public static deletePluginPluginsPluginIdDelete(
        pluginId: string,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/plugins/{plugin_id}',
            path: {
                'plugin_id': pluginId,
            },
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

/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { PluginType } from './PluginType';
/**
 * Response schema.
 */
export type Plugin = {
    metadata_?: ApiJSONObject;
    /**
     * unique plugin name/identifier
     */
    name: string;
    /**
     * what the plugin does
     */
    description?: (string | null);
    /**
     * type of plugin: tool, filter, or hook
     */
    type: PluginType;
    /**
     * plugin author
     */
    author?: (string | null);
    /**
     * plugin version
     */
    version?: (string | null);
    /**
     * python module source containing the plugin class
     */
    source_code: string;
    id: string;
    created_at: string;
    updated_at: string;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { PluginType } from './PluginType';
/**
 * Payload for plugin creation.
 */
export type PluginCreate = {
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
};


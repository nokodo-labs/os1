/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * metadata about an available plugin (native or user-defined).
 */
export type PluginInfo = {
    /**
     * unique plugin identifier
     */
    id: string;
    /**
     * display name of the plugin
     */
    name: string;
    /**
     * what the plugin does
     */
    description: string;
    /**
     * type of plugin: 'tool', 'filter', or 'hook'
     */
    type: 'tool' | 'filter' | 'hook';
    /**
     * whether this plugin is built-in (native) or user-defined
     */
    is_native?: boolean;
};


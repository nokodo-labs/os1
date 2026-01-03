/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PluginType } from './PluginType';
/**
 * Payload for plugin update.
 */
export type PluginUpdate = {
    metadata_?: Record<string, any>;
    name?: (string | null);
    description?: (string | null);
    type?: (PluginType | null);
    author?: (string | null);
    version?: (string | null);
    source_code?: (string | null);
};


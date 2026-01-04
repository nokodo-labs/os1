/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentVisibility } from './AgentVisibility';
/**
 * Payload for agent creation.
 */
export type AgentCreate = {
    metadata_?: Record<string, any>;
    name: string;
    description?: (string | null);
    system_prompt?: (string | null);
    visibility?: AgentVisibility;
    plugin_ids?: Array<string>;
    config?: Record<string, any>;
    model_id?: (string | null);
    profile_image_file_id?: (string | null);
    profile_image_url?: (string | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentVisibility } from './AgentVisibility';
/**
 * Payload for agent update.
 */
export type AgentUpdate = {
    metadata_?: Record<string, any>;
    name?: (string | null);
    description?: (string | null);
    system_prompt?: (string | null);
    visibility?: (AgentVisibility | null);
    plugin_ids?: (Array<string> | null);
    config?: (Record<string, any> | null);
    model_id?: (string | null);
    profile_image_file_id?: (string | null);
    profile_image_url?: (string | null);
};


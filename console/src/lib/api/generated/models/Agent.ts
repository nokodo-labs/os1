/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentVisibility } from './AgentVisibility';
import type { ApiJSONObject } from './ApiJSONObject';
import type { Model } from './Model';
/**
 * Response schema.
 */
export type Agent = {
    metadata_?: ApiJSONObject;
    name: string;
    description?: (string | null);
    system_prompt?: (string | null);
    visibility?: AgentVisibility;
    plugin_ids?: Array<string>;
    config?: Record<string, any>;
    model_id?: (string | null);
    profile_image_file_id?: (string | null);
    profile_image_url?: (string | null);
    id: string;
    created_at: string;
    updated_at: string;
    model?: (Model | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AgentVisibility } from './AgentVisibility';
import type { Model } from './Model';
/**
 * Response schema.
 */
export type Agent = {
    metadata_?: Record<string, any>;
    name: string;
    description?: (string | null);
    system_prompt?: (string | null);
    visibility?: AgentVisibility;
    tool_ids?: Array<string>;
    config?: Record<string, any>;
    model_id?: (string | null);
    id: string;
    created_at: string;
    updated_at: string;
    model?: (Model | null);
};


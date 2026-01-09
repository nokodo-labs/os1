/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Output } from './JSONObject_Output';
/**
 * Response schema.
 */
export type Prompt = {
    metadata_?: JSONObject_Output;
    /**
     * Prompt identifier, e.g. '/my-prompt'
     */
    command: string;
    content: string;
    id: string;
    created_at: string;
    updated_at: string;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * Payload for prompt creation.
 */
export type PromptCreate = {
    metadata_?: ApiJSONObject;
    /**
     * Prompt identifier, e.g. '/my-prompt'
     */
    command: string;
    content: string;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload for prompt creation.
 */
export type PromptCreate = {
    metadata_?: Record<string, any>;
    /**
     * Prompt identifier, e.g. '/my-prompt'
     */
    command: string;
    content: string;
};


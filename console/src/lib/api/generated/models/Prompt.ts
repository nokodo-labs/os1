/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Response schema.
 */
export type Prompt = {
    metadata_?: Record<string, any>;
    /**
     * Prompt identifier, e.g. '/my-prompt'
     */
    command: string;
    content: string;
    id: string;
    created_at: string;
    updated_at: string;
};


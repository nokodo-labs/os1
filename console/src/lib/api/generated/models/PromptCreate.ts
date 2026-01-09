/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
/**
 * Payload for prompt creation.
 */
export type PromptCreate = {
    metadata_?: JSONObject_Input;
    /**
     * Prompt identifier, e.g. '/my-prompt'
     */
    command: string;
    content: string;
};


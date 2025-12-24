/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenAIChatMessage } from './OpenAIChatMessage';
export type OpenAIChatCompletionRequest = {
    model: string;
    messages: Array<OpenAIChatMessage>;
    temperature?: (number | null);
    max_tokens?: (number | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenAIChatCompletionChoice } from './OpenAIChatCompletionChoice';
import type { OpenAIChatCompletionUsage } from './OpenAIChatCompletionUsage';
export type OpenAIChatCompletionResponse = {
    id?: string;
    object?: string;
    created?: number;
    model: string;
    choices: Array<OpenAIChatCompletionChoice>;
    usage?: OpenAIChatCompletionUsage;
};


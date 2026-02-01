/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AIChatContextSettings } from './AIChatContextSettings';
import type { AIMemorySettings } from './AIMemorySettings';
export type AISettings = {
    /**
     * default agent id
     */
    default_agent_id?: (string | null);
    /**
     * AI memory settings
     */
    memory?: AIMemorySettings;
    /**
     * chat context settings
     */
    chat_context?: AIChatContextSettings;
};


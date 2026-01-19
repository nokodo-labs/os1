/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AIChatContextSettingsPatch } from './AIChatContextSettingsPatch';
import type { AIMemorySettingsPatch } from './AIMemorySettingsPatch';
export type AISettingsPatch = {
    /**
     * default agent id
     */
    default_agent_id?: (string | null);
    memory?: (AIMemorySettingsPatch | null);
    chat_context?: (AIChatContextSettingsPatch | null);
};


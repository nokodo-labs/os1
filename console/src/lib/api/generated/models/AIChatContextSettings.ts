/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AIChatContextSettings = {
    /**
     * how chats are selected for Agent context enrichment
     */
    mode?: 'recent' | 'relevant' | 'pinned';
    /**
     * number of chats to use for context enrichment
     */
    top_k?: number;
};


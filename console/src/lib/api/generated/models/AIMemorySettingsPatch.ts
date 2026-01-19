/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AIMemorySettingsPatch = {
    /**
     * enable memory
     */
    enable_memory?: (boolean | null);
    /**
     * similarity minimum threshold for memory retrieval
     */
    similarity_threshold?: (number | null);
    /**
     * number of relevant memories to retrieve
     */
    top_k?: (number | null);
    /**
     * number of recent messages to consider
     */
    messages_to_consider?: (number | null);
};


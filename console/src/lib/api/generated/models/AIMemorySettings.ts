/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AIMemorySettings = {
    /**
     * enable memory
     */
    enable_memory?: boolean;
    /**
     * similarity minimum threshold for memory retrieval. how similar a memory must be to be considered relevant. 0.0 = all memories, 1.0 = exact match
     */
    similarity_threshold?: number;
    /**
     * number of relevant memories to retrieve
     */
    top_k?: number;
    /**
     * number of recent messages to consider when retrieving relevant memories for the agent and for consolidation work
     */
    messages_to_consider?: number;
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Payload to run a thread, optionally appending a new user message.
 */
export type ThreadRunRequest = {
    agent_id?: (string | null);
    model_id?: (string | null);
    model?: (string | null);
    input?: (string | null);
    temperature?: (number | null);
    max_tokens?: (number | null);
};


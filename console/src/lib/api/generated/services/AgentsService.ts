/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Agent } from '../models/Agent';
import type { AgentCreate } from '../models/AgentCreate';
import type { AgentUpdate } from '../models/AgentUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AgentsService {
    /**
     * List Agents
     * List all agents.
     * @returns Agent Successful Response
     * @throws ApiError
     */
    public static listAgentsAgentsGet(): CancelablePromise<Array<Agent>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/agents',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Create Agent
     * Register a new agent.
     * @param requestBody
     * @returns Agent Successful Response
     * @throws ApiError
     */
    public static createAgentAgentsPost(
        requestBody: AgentCreate,
    ): CancelablePromise<Agent> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/agents',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Get Agent
     * Fetch an agent.
     * @param agentId
     * @returns Agent Successful Response
     * @throws ApiError
     */
    public static getAgentAgentsAgentIdGet(
        agentId: string,
    ): CancelablePromise<Agent> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/agents/{agent_id}',
            path: {
                'agent_id': agentId,
            },
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
    /**
     * Update Agent
     * Update an agent.
     * @param agentId
     * @param requestBody
     * @returns Agent Successful Response
     * @throws ApiError
     */
    public static updateAgentAgentsAgentIdPatch(
        agentId: string,
        requestBody: AgentUpdate,
    ): CancelablePromise<Agent> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/agents/{agent_id}',
            path: {
                'agent_id': agentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `bad request`,
                401: `unauthorized`,
                403: `forbidden`,
                404: `not found`,
                409: `conflict`,
                422: `validation error`,
                429: `too many requests`,
                500: `internal server error`,
            },
        });
    }
}

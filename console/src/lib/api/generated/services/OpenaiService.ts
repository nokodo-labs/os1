/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OpenAIChatCompletionRequest } from '../models/OpenAIChatCompletionRequest';
import type { OpenAIChatCompletionResponse } from '../models/OpenAIChatCompletionResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OpenaiService {
    /**
     * Chat Completions
     * @param requestBody
     * @returns OpenAIChatCompletionResponse Successful Response
     * @throws ApiError
     */
    public static chatCompletionsOpenaiChatCompletionsPost(
        requestBody: OpenAIChatCompletionRequest,
    ): CancelablePromise<OpenAIChatCompletionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/openai/chat/completions',
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

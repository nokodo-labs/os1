/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
/**
 * Request payload to fetch events for a set of messages.
 */
export type EventsByMessageIDsRequest = {
    metadata_?: ApiJSONObject;
    message_ids?: Array<string>;
};


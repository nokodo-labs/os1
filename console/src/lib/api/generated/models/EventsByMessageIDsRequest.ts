/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
/**
 * Request payload to fetch events for a set of messages.
 */
export type EventsByMessageIDsRequest = {
    metadata_?: JSONObject_Input;
    message_ids?: Array<string>;
};


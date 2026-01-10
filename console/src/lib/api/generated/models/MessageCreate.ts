/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { MessageType } from './MessageType';
/**
 * Payload for creating a message within a thread.
 *
 * Content can be provided as:
 * - A string (converted to [TextContent(text=...)])
 * - A list of content part dicts or ContentPart objects
 */
export type MessageCreate = {
    metadata_?: ApiJSONObject;
    type?: MessageType;
    content?: string;
    tool_calls?: Array<Record<string, any>>;
    usage?: (Record<string, any> | null);
    read_by?: Array<string>;
    parent_id?: (string | null);
    task_id?: (string | null);
    sender_agent_id?: (string | null);
    sender_user_id?: (string | null);
};


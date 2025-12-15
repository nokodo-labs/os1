/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MessageType } from './MessageType';
/**
 * Payload for creating a message within a thread.
 */
export type MessageCreate = {
    metadata_?: Record<string, any>;
    type?: MessageType;
    content: string;
    attachments?: Array<Record<string, any>>;
    tool_calls?: Array<Record<string, any>>;
    token_usage?: (Record<string, any> | null);
    read_by?: Array<number>;
    task_id?: (string | null);
    sender_agent_id?: (string | null);
    sender_user_id?: (number | null);
};


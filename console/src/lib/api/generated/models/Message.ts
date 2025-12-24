/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FileContent } from './FileContent';
import type { ImageContent } from './ImageContent';
import type { JsonContent } from './JsonContent';
import type { MessageType } from './MessageType';
import type { RefusalContent } from './RefusalContent';
import type { TextContent } from './TextContent';
/**
 * Response schema.
 */
export type Message = {
    metadata_?: Record<string, any>;
    type?: MessageType;
    content?: Array<(TextContent | JsonContent | ImageContent | FileContent | RefusalContent)>;
    tool_calls?: Array<Record<string, any>>;
    usage?: (Record<string, any> | null);
    read_by?: Array<string>;
    id: string;
    thread_id: string;
    parent_id?: (string | null);
    task_id?: (string | null);
    sender_agent_id?: (string | null);
    sender_user_id?: (string | null);
    created_at: string;
    updated_at: string;
};


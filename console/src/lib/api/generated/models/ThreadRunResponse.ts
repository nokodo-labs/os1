/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Message } from './Message';
/**
 * response containing all messages produced by a run.
 *
 * an agent run can produce multiple messages:
 * - assistant message with tool calls
 * - tool result messages
 * - more assistant messages
 * - ... repeat until final assistant message
 *
 * the messages list contains all new messages produced during the run.
 */
export type ThreadRunResponse = {
    thread_id: string;
    user_message?: (Message | null);
    messages: Array<Message>;
};


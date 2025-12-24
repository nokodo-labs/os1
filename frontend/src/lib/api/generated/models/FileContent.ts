/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * file attachment content.
 *
 * for ORM storage: metadata["file_id"] is set, url/base64 may be null
 * for SDK execution: url or base64 must be populated (resolved from file_id)
 * for external files: url is set, no file_id in metadata
 */
export type FileContent = {
    metadata?: (Record<string, any> | null);
    type?: string;
    url?: (string | null);
    base64?: (string | null);
    filename?: (string | null);
    media_type?: (string | null);
};


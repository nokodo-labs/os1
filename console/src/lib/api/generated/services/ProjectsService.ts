/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AccessControlEntry } from '../models/AccessControlEntry';
import type { AccessControlEntryCreate } from '../models/AccessControlEntryCreate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ProjectsService {
    /**
     * List Project Acl
     * List acl entries for a project.
     * @param projectId
     * @returns AccessControlEntry Successful Response
     * @throws ApiError
     */
    public static listProjectAclProjectsProjectIdAclGet(
        projectId: string,
    ): CancelablePromise<Array<AccessControlEntry>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/projects/{project_id}/acl',
            path: {
                'project_id': projectId,
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
     * Set Project Acl
     * Replace acl entries for a project.
     * @param projectId
     * @param requestBody
     * @returns AccessControlEntry Successful Response
     * @throws ApiError
     */
    public static setProjectAclProjectsProjectIdAclPut(
        projectId: string,
        requestBody: Array<AccessControlEntryCreate>,
    ): CancelablePromise<Array<AccessControlEntry>> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/projects/{project_id}/acl',
            path: {
                'project_id': projectId,
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

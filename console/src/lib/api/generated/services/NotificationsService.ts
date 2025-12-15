/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Notification } from '../models/Notification';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class NotificationsService {
    /**
     * List User Notifications
     * Return notifications for a user.
     * @param userId
     * @param onlyUnread
     * @returns Notification Successful Response
     * @throws ApiError
     */
    public static listUserNotificationsNotificationsUsersUserIdGet(
        userId: number,
        onlyUnread: boolean = false,
    ): CancelablePromise<Array<Notification>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/notifications/users/{user_id}',
            path: {
                'user_id': userId,
            },
            query: {
                'only_unread': onlyUnread,
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
     * Mark Notification Read
     * Mark a notification as read.
     * @param notificationId
     * @returns Notification Successful Response
     * @throws ApiError
     */
    public static markNotificationReadNotificationsNotificationIdReadPost(
        notificationId: string,
    ): CancelablePromise<Notification> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/notifications/{notification_id}/read',
            path: {
                'notification_id': notificationId,
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
     * Dismiss Notification
     * Dismiss a notification without marking it read.
     * @param notificationId
     * @returns Notification Successful Response
     * @throws ApiError
     */
    public static dismissNotificationNotificationsNotificationIdDismissPost(
        notificationId: string,
    ): CancelablePromise<Notification> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/notifications/{notification_id}/dismiss',
            path: {
                'notification_id': notificationId,
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
}

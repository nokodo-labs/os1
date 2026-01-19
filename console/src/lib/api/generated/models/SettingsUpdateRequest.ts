/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SettingsPatch } from './SettingsPatch';
import type { SettingsVersions } from './SettingsVersions';
export type SettingsUpdateRequest = {
    data: SettingsPatch;
    expected_versions?: (SettingsVersions | null);
};


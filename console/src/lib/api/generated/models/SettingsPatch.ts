/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AISettingsPatch } from './AISettingsPatch';
import type { BrandingSettingsPatch } from './BrandingSettingsPatch';
import type { FeaturesSettingsPatch } from './FeaturesSettingsPatch';
import type { LimitsSettingsPatch } from './LimitsSettingsPatch';
import type { SecuritySettingsPatch } from './SecuritySettingsPatch';
import type { UISettingsPatch } from './UISettingsPatch';
export type SettingsPatch = {
    ui?: (UISettingsPatch | null);
    features?: (FeaturesSettingsPatch | null);
    ai?: (AISettingsPatch | null);
    branding?: (BrandingSettingsPatch | null);
    limits?: (LimitsSettingsPatch | null);
    security?: (SecuritySettingsPatch | null);
};


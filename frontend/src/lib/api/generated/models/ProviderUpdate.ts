/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProviderStatus } from './ProviderStatus';
import type { ProviderType } from './ProviderType';
/**
 * Partial provider update payload.
 */
export type ProviderUpdate = {
    metadata_?: Record<string, any>;
    adapter_type?: (string | null);
    provider_type?: (ProviderType | null);
    base_url?: (string | null);
    api_key?: (string | null);
    encrypted_api_key?: (string | null);
    model_prefix?: (string | null);
    additional_headers?: (Record<string, string> | null);
    status?: (ProviderStatus | null);
    is_autofetch_enabled?: (boolean | null);
    last_synced_at?: (string | null);
};


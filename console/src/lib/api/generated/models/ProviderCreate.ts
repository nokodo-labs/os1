/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Input } from './JSONObject_Input';
import type { ProviderStatus } from './ProviderStatus';
import type { ProviderType } from './ProviderType';
/**
 * Payload to create a provider.
 */
export type ProviderCreate = {
    metadata_?: JSONObject_Input;
    name: string;
    adapter_type: string;
    provider_type?: ProviderType;
    base_url?: (string | null);
    encrypted_api_key?: (string | null);
    model_prefix?: (string | null);
    additional_headers?: (Record<string, string> | null);
    status?: ProviderStatus;
    is_autofetch_enabled?: boolean;
    last_synced_at?: (string | null);
    api_key?: (string | null);
};


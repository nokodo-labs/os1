/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { JSONObject_Output } from './JSONObject_Output';
import type { ModelType } from './ModelType';
/**
 * Response schema.
 */
export type Model = {
    metadata_?: JSONObject_Output;
    name: string;
    display_name?: (string | null);
    model_type?: ModelType;
    endpoint?: (string | null);
    capabilities?: Array<string>;
    context_window?: (number | null);
    input_cost?: (number | null);
    output_cost?: (number | null);
    enabled?: boolean;
    is_autofetched?: boolean;
    id: string;
    provider_id: string;
    created_at: string;
    updated_at: string;
};


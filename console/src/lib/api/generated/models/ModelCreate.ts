/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ApiJSONObject } from './ApiJSONObject';
import type { ModelType } from './ModelType';
/**
 * Payload to register a model.
 */
export type ModelCreate = {
    metadata_?: ApiJSONObject;
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
    provider_id: string;
};


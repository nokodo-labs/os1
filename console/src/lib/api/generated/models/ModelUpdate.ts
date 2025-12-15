/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ModelType } from './ModelType';
/**
 * Payload to update a model.
 */
export type ModelUpdate = {
    metadata_?: Record<string, any>;
    name?: (string | null);
    display_name?: (string | null);
    model_type?: (ModelType | null);
    endpoint?: (string | null);
    capabilities?: (Array<string> | null);
    context_window?: (number | null);
    input_cost?: (number | null);
    output_cost?: (number | null);
    enabled?: (boolean | null);
    is_autofetched?: (boolean | null);
};


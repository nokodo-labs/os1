/**
 * per-resource-type export options.
 *
 * a resource type declares what its export can be tuned by; the share modal
 * renders whatever it declares and hands the chosen values to the snapshot
 * builders. definitions reach their own field of `ExportOptionValues` through
 * `read`/`write`, so the record stays a typed shape rather than a string-keyed bag.
 */

import Branch from '$lib/components/icons/Branch.svelte'
import ChatBubbles from '$lib/components/icons/ChatBubbles.svelte'
import Tree from '$lib/components/icons/Tree.svelte'
import type { ResourceAccessPayload } from '$lib/stores/modals.svelte'
import type { Component } from 'svelte'

type ResourceType = ResourceAccessPayload['resourceType']

/** every icon in the set takes a class; that is all an option needs from one. */
export type ExportOptionIcon = Component<{ class?: string }>

/** how much of a thread an export covers: the visible path, or every branch. */
export type ThreadExportScope = 'branch' | 'tree'

/** one field per declared option, across every resource type. */
export interface ExportOptionValues {
	threadScope: ThreadExportScope
}

export const BASE_EXPORT_OPTION_VALUES: ExportOptionValues = { threadScope: 'branch' }

export interface ExportOptionChoice<Value extends string = string> {
	id: Value
	label: string
	icon: ExportOptionIcon
}

export interface ExportOptionDefinition<Value extends string = string> {
	id: string
	label: string
	icon: ExportOptionIcon
	kind: 'single-choice'
	choices: readonly ExportOptionChoice<Value>[]
	defaultChoice: Value
	read: (values: ExportOptionValues) => Value
	write: (values: ExportOptionValues, choice: string) => ExportOptionValues
}

/** what the export panel needs to render and update the declared options. */
export interface ExportOptionsBinding {
	definitions: readonly ExportOptionDefinition[]
	values: ExportOptionValues
	onchange: (definition: ExportOptionDefinition, choice: string) => void
}

export function toThreadExportScope(value: string): ThreadExportScope {
	return value === 'tree' ? 'tree' : 'branch'
}

const THREAD_SCOPE_OPTION: ExportOptionDefinition<ThreadExportScope> = {
	id: 'thread-scope',
	label: 'messages',
	icon: ChatBubbles,
	kind: 'single-choice',
	choices: [
		{ id: 'branch', label: 'this branch', icon: Branch },
		{ id: 'tree', label: 'all branches', icon: Tree },
	],
	defaultChoice: 'branch',
	read: (values) => values.threadScope,
	write: (values, choice) => ({ ...values, threadScope: toThreadExportScope(choice) }),
}

export function exportOptionsFor(
	resourceType: ResourceType | undefined
): readonly ExportOptionDefinition[] {
	return resourceType === 'thread' ? [THREAD_SCOPE_OPTION] : []
}

export function defaultExportOptionValues(
	resourceType: ResourceType | undefined
): ExportOptionValues {
	return exportOptionsFor(resourceType).reduce(
		(values, definition) => definition.write(values, definition.defaultChoice),
		BASE_EXPORT_OPTION_VALUES
	)
}

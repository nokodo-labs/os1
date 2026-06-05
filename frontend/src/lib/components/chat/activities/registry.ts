import type { RunActivityState } from '$lib/chat'
import type { Component } from 'svelte'
import ContextCompactionActivity from './ContextCompactionActivity.svelte'
import GenericRunActivity from './GenericRunActivity.svelte'
import MemoryMaintenanceActivity from './MemoryMaintenanceActivity.svelte'

export type RunActivityRenderer = Component<{ activity: RunActivityState }>

interface RunActivityDefinition {
	renderer: RunActivityRenderer
}

const nativeRunActivities = new Map<string, RunActivityDefinition>([
	['context_compaction', { renderer: ContextCompactionActivity }],
	['memory_maintenance', { renderer: MemoryMaintenanceActivity }],
])

export function getRunActivityRenderer(activityType: string): RunActivityRenderer {
	return nativeRunActivities.get(activityType)?.renderer ?? GenericRunActivity
}

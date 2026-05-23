import type { RunActivityState } from '$lib/chat'
import ContextCompactionActivity from '$lib/components/chat/activities/ContextCompactionActivity.svelte'
import GenericRunActivity from '$lib/components/chat/activities/GenericRunActivity.svelte'
import RunActivity from '$lib/components/chat/activities/RunActivity.svelte'
import { getRunActivityRenderer } from '$lib/components/chat/activities/registry'
import { render, screen } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

function makeActivity(overrides: Partial<RunActivityState> = {}): RunActivityState {
	const startedAt = new Date(0)
	return {
		key: 'activity_1',
		id: 'event_1',
		eventIds: ['event_1'],
		messageId: 'message_1',
		runId: 'run_1',
		activityId: 'activity_1',
		activityType: 'plugin_activity',
		status: 'running',
		startedAt,
		updatedAt: startedAt,
		...overrides,
	}
}

describe('run activity renderers', () => {
	it('routes context compaction through its native renderer', () => {
		expect(getRunActivityRenderer('context_compaction')).toBe(ContextCompactionActivity)

		render(RunActivity, {
			props: {
				activity: makeActivity({
					activityType: 'context_compaction',
					title: 'compacting chat',
					message: 'summarizing old context',
				}),
			},
		})

		expect(screen.getByText('compacting chat')).toBeTruthy()
		expect(screen.queryByText('summarizing old context')).toBeNull()
	})

	it('renders unknown activity types with the generic fallback', () => {
		expect(getRunActivityRenderer('plugin_long_task')).toBe(GenericRunActivity)

		render(RunActivity, {
			props: {
				activity: makeActivity({
					activityType: 'plugin_long_task',
					status: 'success',
					message: 'indexing files',
					updatedAt: new Date(3000),
					endedAt: new Date(3000),
					outcome: 'success',
				}),
			},
		})

		expect(screen.getByText('indexing files completed in 3s')).toBeTruthy()
	})
})

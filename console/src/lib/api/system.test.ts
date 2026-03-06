import { describe, expect, it } from 'vitest'

import { SystemService } from './system'

describe('SystemService', () => {
	it('exposes getSystemStatus', () => {
		expect(typeof SystemService.getSystemStatus).toBe('function')
	})
})

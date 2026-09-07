import { classifyRenderer, resolveGpuTier } from '$lib/utils/gpuTier'
import { describe, expect, it } from 'vitest'

const XPS =
	'ANGLE (Intel, Intel(R) Iris(R) Xe Graphics (0x0000A7A0) Direct3D11 vs_5_0 ps_5_0, D3D11)'
const DESKTOP =
	'ANGLE (NVIDIA, NVIDIA GeForce RTX 5090 (0x00002B85) Direct3D11 vs_5_0 ps_5_0, D3D11)'

describe('classifyRenderer', () => {
	it('tells igpus from cards', () => {
		expect(classifyRenderer(XPS)).toBe('integrated')
		expect(classifyRenderer(DESKTOP)).toBe('discrete')
		expect(classifyRenderer('ANGLE (Intel, Intel(R) Arc(TM) A770 Graphics Direct3D11)')).toBe(
			'discrete'
		)
		expect(classifyRenderer('ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11)')).toBe(
			'integrated'
		)
		expect(classifyRenderer('ANGLE (AMD, AMD Radeon RX 7800 XT Direct3D11)')).toBe('discrete')
		expect(classifyRenderer('ANGLE (ARM, Mali-G715, OpenGL ES 3.2)')).toBe('mobile')
		expect(classifyRenderer('ANGLE (Qualcomm, Adreno (TM) 660, OpenGL ES 3.2)')).toBe('mobile')
		expect(classifyRenderer('Apple M2')).toBe('apple')
		expect(classifyRenderer('Google SwiftShader')).toBe('software')
		expect(classifyRenderer(null)).toBe('unknown')
	})
})

describe('resolveGpuTier', () => {
	it('never grades an igpu high, whatever the cpu and memory say', () => {
		// the xps 13 row: 16 threads, 32gb, iris xe -> score 7
		expect(resolveGpuTier(7, 'integrated').tier).toBe('mid')
	})

	it('keeps an igpu at mid regardless of dpr', () => {
		expect(resolveGpuTier(7, 'integrated').tier).toBe('mid')
	})

	it('keeps cards and apple silicon on the score', () => {
		expect(resolveGpuTier(9, 'discrete').tier).toBe('high')
		expect(resolveGpuTier(9, 'discrete').tier).toBe('high')
		expect(resolveGpuTier(6, 'apple').tier).toBe('high')
	})

	it('leaves phones at mid regardless of dpr', () => {
		expect(resolveGpuTier(0, 'mobile').tier).toBe('mid')
		expect(resolveGpuTier(1, 'mobile').tier).toBe('mid')
	})

	it('caps an unreadable renderer at mid and software at low', () => {
		expect(resolveGpuTier(7, 'unknown').tier).toBe('mid')
		expect(resolveGpuTier(7, 'software').tier).toBe('low')
		expect(resolveGpuTier(-2, 'discrete').tier).toBe('low')
	})
})

/**
 * gpu tier grading. the renderer decides the ceiling; cores and memory only
 * refine within it, because they say nothing about what an integrated gpu can
 * blur, and blur is what this ui spends its frames on.
 */

export type GpuTier = 'high' | 'mid' | 'low'

export type GpuClass = 'discrete' | 'apple' | 'integrated' | 'mobile' | 'software' | 'unknown'

export function classifyRenderer(renderer: string | null): GpuClass {
	if (!renderer) return 'unknown'
	const lower = renderer.toLowerCase()
	if (lower.includes('swiftshader') || lower.includes('llvmpipe') || lower.includes('software')) {
		return 'software'
	}
	if (lower.includes('rtx') || lower.includes('geforce') || lower.includes('nvidia'))
		return 'discrete'
	if (lower.includes('apple')) return 'apple'
	if (lower.includes('adreno') || lower.includes('mali') || lower.includes('powervr'))
		return 'mobile'
	// intel arc cards are "arc(tm) a770"; everything else intel is an igpu
	if (lower.includes('intel'))
		return /\barc(\(tm\))? [ab]\d/.test(lower) ? 'discrete' : 'integrated'
	// "amd radeon(tm) graphics" and vega are igpus; rx and rdna parts are cards
	if (lower.includes('radeon') || lower.includes('rdna')) {
		return /\brx\s?\d/.test(lower) || lower.includes('rdna') ? 'discrete' : 'integrated'
	}
	return 'unknown'
}

export function resolveGpuTier(
	score: number,
	gpuClass: GpuClass
): { tier: GpuTier; notes: string[] } {
	const notes: string[] = []
	let tier: GpuTier = score >= 5 ? 'high' : score <= -1 ? 'low' : 'mid'
	if (gpuClass === 'software') {
		tier = 'low'
		notes.push('software renderer -> low')
		return { tier, notes }
	}
	if (gpuClass === 'discrete' || gpuClass === 'apple') return { tier, notes }
	if (tier === 'high') {
		tier = 'mid'
		notes.push(`${gpuClass} gpu caps at mid`)
	}
	return { tier, notes }
}

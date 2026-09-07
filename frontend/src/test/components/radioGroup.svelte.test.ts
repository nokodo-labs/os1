import CssRadioGroup from '$lib/components/primitives/CssRadioGroup.svelte'
import LiquidGlassRadioGroup from '$lib/components/primitives/liquid-glass/RadioGroup.svelte'
import { render } from '@testing-library/svelte'
import type { Component } from 'svelte'
import { describe, expect, it, vi } from 'vitest'

const options = [
	{ value: 'none', label: 'none' },
	{ value: 'whatsapp', label: 'whatsapp' },
	{ value: 'imessage', label: 'imessage' },
] as const

function radios(container: HTMLElement): HTMLElement[] {
	return Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]'))
}

const variants: [string, Component][] = [
	['CssRadioGroup', CssRadioGroup as unknown as Component],
	['liquid-glass RadioGroup', LiquidGlassRadioGroup as unknown as Component],
]

describe.each(variants)('%s', (_name, RadioGroup) => {
	it('renders one radio per option inside a radiogroup', () => {
		const { container } = render(RadioGroup, {
			props: { options, value: 'imessage', onchange: () => {} },
		})

		expect(radios(container)).toHaveLength(3)
		expect(container.querySelector('[role="radiogroup"]')).not.toBeNull()
		expect(radios(container)[2]?.getAttribute('aria-checked')).toBe('true')
		expect(radios(container)[0]?.getAttribute('aria-checked')).toBe('false')
	})

	it('wraps options onto a new row instead of overflowing a narrow viewport', () => {
		const { container } = render(RadioGroup, {
			props: { options, value: 'none', onchange: () => {} },
		})

		const group = container.querySelector('[role="radiogroup"]')
		expect(group?.className).toContain('flex-wrap')
		expect(group?.className).toContain('gap-2')
	})

	it('stretches every option across its row without squeezing it', () => {
		const { container } = render(RadioGroup, {
			props: { options, value: 'none', onchange: () => {} },
		})

		for (const radio of radios(container)) {
			expect(radio.className).toContain('flex-1')
			expect(radio.className).toContain('min-w-fit')
			expect(radio.className).not.toContain('flex-none')
		}
	})

	it('keeps the caller class on the wrapping row', () => {
		const { container } = render(RadioGroup, {
			props: { options, value: 'none', onchange: () => {}, class: 'mt-4' },
		})

		const group = container.querySelector('[role="radiogroup"]')
		expect(group?.className).toContain('flex-wrap')
		expect(group?.className).toContain('mt-4')
	})

	it('selects an option and clears it back when clearValue is given', () => {
		const onchange = vi.fn()
		const { container } = render(RadioGroup, {
			props: { options, value: 'whatsapp', onchange, clearValue: 'none' },
		})

		radios(container)[2]?.click()
		expect(onchange).toHaveBeenCalledWith('imessage')

		onchange.mockClear()
		radios(container)[1]?.click()
		expect(onchange).toHaveBeenCalledWith('none')
	})
})

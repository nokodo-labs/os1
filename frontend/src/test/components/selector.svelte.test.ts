import Selector, { type SelectorOption } from '$lib/components/primitives/Selector.svelte'
import { render } from '@testing-library/svelte'
import { describe, expect, it, vi } from 'vitest'

const options: SelectorOption[] = [
	{ value: 'a', label: 'first option' },
	{ value: 'b', label: 'second option', description: 'https://a-very-long-unbreakable-origin' },
	{ value: 'c', label: 'third option', disabled: true },
]

function radios(container: HTMLElement): HTMLElement[] {
	return Array.from(container.querySelectorAll<HTMLElement>('[role="radio"]'))
}

describe('Selector', () => {
	it('renders one radio per option inside a labelled radiogroup', () => {
		const { container } = render(Selector, {
			props: { options, value: 'a', onchange: () => {}, ariaLabel: 'pick one' },
		})

		expect(radios(container)).toHaveLength(3)
		const group = container.querySelector('[role="radiogroup"]')
		expect(group?.getAttribute('aria-label')).toBe('pick one')
		expect(radios(container)[0]?.getAttribute('aria-checked')).toBe('true')
		expect(radios(container)[1]?.getAttribute('aria-checked')).toBe('false')
	})

	it('stacks options in one column and sizes columns off the container, not the viewport', () => {
		const { container } = render(Selector, {
			props: { options, value: 'a', onchange: () => {}, columns: 'two' },
		})

		expect(container.firstElementChild?.className).toContain('@container/selector')
		const group = container.querySelector('[role="radiogroup"]')
		expect(group?.className).toContain('grid-cols-1')
		expect(group?.className).toContain('@min-[30rem]/selector:grid-cols-2')
		expect(group?.className).not.toContain('sm:grid-cols-2')
	})

	it('keeps a single column when the caller asks for one', () => {
		const { container } = render(Selector, {
			props: { options, value: 'a', onchange: () => {} },
		})

		const group = container.querySelector('[role="radiogroup"]')
		expect(group?.className).toContain('grid-cols-1')
		expect(group?.className).not.toContain('grid-cols-2')
	})

	it('reflows an option to a stacked layout when the container is too narrow for a row', () => {
		const { container } = render(Selector, {
			props: { options, value: 'a', onchange: () => {} },
		})
		const [option] = radios(container)

		expect(option?.className).toContain('flex-wrap')
		expect(option?.className).toContain('min-w-0')

		const label = option?.children[1]
		expect(label?.className).toContain('basis-full')
		expect(label?.className).toContain('order-last')
		expect(label?.className).toContain('break-words')
		expect(label?.className).toContain('@min-[13rem]/selector:flex-1')
		expect(label?.className).toContain('@min-[13rem]/selector:basis-auto')
		expect(label?.className).toContain('@min-[13rem]/selector:order-none')
	})

	it('selects an enabled option and ignores a disabled one', async () => {
		const onchange = vi.fn()
		const { container } = render(Selector, { props: { options, value: 'a', onchange } })
		const [, second, third] = radios(container)

		second?.click()
		expect(onchange).toHaveBeenCalledWith('b')

		onchange.mockClear()
		third?.click()
		expect(onchange).not.toHaveBeenCalled()
	})

	it('ignores every option while the whole selector is disabled', () => {
		const onchange = vi.fn()
		const { container } = render(Selector, {
			props: { options, value: 'a', onchange, disabled: true },
		})

		radios(container)[1]?.click()
		expect(onchange).not.toHaveBeenCalled()
	})
})

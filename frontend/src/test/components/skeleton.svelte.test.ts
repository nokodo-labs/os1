import Skeleton from '$lib/components/primitives/Skeleton.svelte'
import { render } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

function items(container: HTMLElement): HTMLElement[] {
	return Array.from(container.querySelectorAll<HTMLElement>('[data-skeleton]'))
}

describe('Skeleton', () => {
	it('renders one item per count and no container of its own', () => {
		const { container } = render(Skeleton, { props: { count: 6 } })

		expect(items(container)).toHaveLength(6)
		expect(container.children).toHaveLength(6)
	})

	it('keeps the frosted glass pulse of the resource placeholders', () => {
		const { container } = render(Skeleton, { props: { shape: 'card' } })
		const [card] = items(container)

		expect(card?.className).toContain('liquid-glass--frosted')
		expect(card?.className).toContain('animate-pulse')
		expect(card?.className).toContain('h-80')
	})

	it('shapes a row as an avatar with stacked text lines', () => {
		const { container } = render(Skeleton, { props: { shape: 'row', lines: 2 } })
		const [row] = items(container)

		expect(row?.querySelectorAll('.rounded-circle')).toHaveLength(1)
		expect(row?.querySelectorAll('.rounded-pill')).toHaveLength(2)
	})

	it('drops the avatar and adds a trailing pill on request', () => {
		const { container } = render(Skeleton, {
			props: { shape: 'row', avatar: false, lines: 1, trailing: true },
		})
		const [row] = items(container)

		expect(row?.querySelectorAll('.rounded-circle')).toHaveLength(0)
		expect(row?.querySelectorAll('.rounded-pill')).toHaveLength(2)
	})

	it('lets explicit sizes override the preset', () => {
		const { container } = render(Skeleton, {
			props: { shape: 'pill', width: '12rem', height: '2rem' },
		})
		const [pill] = items(container)

		expect(pill?.style.width).toBe('12rem')
		expect(pill?.style.height).toBe('2rem')
		expect(pill?.className).toContain('rounded-pill')
	})

	it('pushes an outgoing bubble to the trailing edge', () => {
		const { container } = render(Skeleton, { props: { shape: 'bubble', align: 'end' } })
		const [bubble] = items(container)

		expect(bubble?.className).toContain('ml-auto')
	})

	it('hides placeholders from assistive tech', () => {
		const { container } = render(Skeleton, { props: { shape: 'lines', count: 2 } })

		for (const item of items(container)) {
			expect(item.getAttribute('aria-hidden')).toBe('true')
		}
	})
})

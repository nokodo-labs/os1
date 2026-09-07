import ChatInput from '$lib/components/chat/ChatInput.svelte'
import { device } from '$lib/stores/device.svelte'
import { fireEvent, render, screen } from '@testing-library/svelte'
import { tick } from 'svelte'
import { afterEach, describe, expect, it } from 'vitest'

const EXAMPLES = ["what's on my calendar friday", 'make a note about the trip']

function mount(props: Record<string, unknown> = {}) {
	return render(ChatInput, {
		props: {
			value: '',
			placeholder: 'send a message',
			placeholderExamples: EXAMPLES,
			...props,
		},
	})
}

function layer(container: HTMLElement): Element | null {
	return container.querySelector('[data-placeholder-rotation]')
}

afterEach(() => {
	device.prefersReducedMotion = false
})

describe('rotating placeholder overlay', () => {
	it('draws an example over the composer while the field is empty', async () => {
		const { container } = mount()
		await tick()

		const rotating = layer(container)
		expect(rotating).not.toBeNull()
		expect(EXAMPLES).toContain(rotating?.textContent?.trim())
	})

	it('leaves the native placeholder in place for assistive tech, just invisible', async () => {
		const { container } = mount()
		await tick()

		const textarea = screen.getByRole('textbox')
		expect(textarea).toHaveAttribute('placeholder', 'send a message')
		expect(textarea).toHaveClass('placeholder:text-transparent')
		expect(layer(container)).toHaveAttribute('aria-hidden', 'true')
	})

	it('drops the overlay the moment something is typed', async () => {
		const { container } = mount()
		await tick()
		expect(layer(container)).not.toBeNull()

		await fireEvent.input(screen.getByRole('textbox'), { target: { value: 'h' } })

		expect(layer(container)).toBeNull()
		expect(screen.getByRole('textbox')).toHaveClass('placeholder:text-foreground/40')
	})

	it('stays out of composers that pass no examples', async () => {
		const { container } = mount({ placeholderExamples: [] })
		await tick()

		expect(layer(container)).toBeNull()
		expect(screen.getByRole('textbox')).toHaveAttribute('placeholder', 'send a message')
	})

	it('never rotates in find mode', async () => {
		const { container } = mount({ mode: 'search', placeholder: 'search anything' })
		await tick()

		expect(layer(container)).toBeNull()
	})

	it('still shows a line under reduced motion', async () => {
		device.prefersReducedMotion = true
		const { container } = mount()
		await tick()

		expect(EXAMPLES).toContain(layer(container)?.textContent?.trim())
	})
})

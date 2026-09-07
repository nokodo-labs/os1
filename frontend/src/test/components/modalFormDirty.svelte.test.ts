import { ModalFormDirty, sameFormValues } from '$lib/components/modals/formDirty.svelte'
import ModalSaveButton from '$lib/components/modals/ModalSaveButton.svelte'
import { render } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'

describe('sameFormValues', () => {
	it('compares primitives and treats null and undefined as different', () => {
		expect(sameFormValues({ a: 'x', b: 1, c: true }, { a: 'x', b: 1, c: true })).toBe(true)
		expect(sameFormValues({ a: 'x' }, { a: 'y' })).toBe(false)
		expect(sameFormValues({ a: null }, { a: undefined })).toBe(false)
	})

	it('compares arrays in order', () => {
		expect(sameFormValues({ tags: ['a', 'b'] }, { tags: ['a', 'b'] })).toBe(true)
		expect(sameFormValues({ tags: ['a', 'b'] }, { tags: ['b', 'a'] })).toBe(false)
		expect(sameFormValues({ tags: ['a'] }, { tags: ['a', 'b'] })).toBe(false)
	})

	it('compares nested records and counts missing keys', () => {
		expect(
			sameFormValues(
				{ rule: { freq: 'weekly', by: [1, 2] } },
				{ rule: { freq: 'weekly', by: [1, 2] } }
			)
		).toBe(true)
		expect(sameFormValues({ rule: { freq: 'weekly' } }, { rule: { freq: 'daily' } })).toBe(
			false
		)
		expect(sameFormValues({ a: 1 }, { a: 1, b: 2 })).toBe(false)
	})
})

describe('ModalFormDirty', () => {
	it('stays clean until a value differs from the snapshot', () => {
		let title = $state('note')
		const form = new ModalFormDirty(() => ({ title }))

		expect(form.dirty).toBe(false)
		form.reset()
		expect(form.dirty).toBe(false)

		title = 'renamed'
		expect(form.dirty).toBe(true)

		title = 'note'
		expect(form.dirty).toBe(false)
	})

	it('snapshots arrays by value, so in-place edits count as dirty', () => {
		const labels = $state(['a'])
		const form = new ModalFormDirty(() => ({ labels }))
		form.reset()

		labels.push('b')
		expect(form.dirty).toBe(true)

		labels.pop()
		expect(form.dirty).toBe(false)
	})

	it('re-baselines on reset, so a saved form is clean again', () => {
		let name = $state('one')
		const form = new ModalFormDirty(() => ({ name }))
		form.reset()

		name = 'two'
		expect(form.dirty).toBe(true)

		form.reset()
		expect(form.dirty).toBe(false)
	})
})

describe('ModalSaveButton', () => {
	function button(container: HTMLElement): HTMLButtonElement | null {
		return container.querySelector('button')
	}

	it('is inert with an explained reason while the form is clean', () => {
		const { container } = render(ModalSaveButton, { props: { dirty: false } })
		const el = button(container)

		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('aria-label')).toBe('save, no changes to save')
		expect(el?.getAttribute('title')).toBe('no changes to save')
		expect(el?.hasAttribute('disabled')).toBe(false)
	})

	it('acts once the form is dirty', () => {
		const { container } = render(ModalSaveButton, { props: { dirty: true } })
		const el = button(container)

		expect(el?.getAttribute('aria-disabled')).toBe('false')
		expect(el?.getAttribute('aria-label')).toBe(null)
		expect(el?.textContent).toContain('save')
	})

	it('prefers a modal reason over the clean-form one', () => {
		const { container } = render(ModalSaveButton, {
			props: { dirty: true, blockedReason: 'name is required' },
		})
		const el = button(container)

		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('title')).toBe('name is required')
	})

	it('explains itself while a save is in flight', () => {
		const { container } = render(ModalSaveButton, { props: { dirty: true, saving: true } })
		const el = button(container)

		expect(el?.getAttribute('aria-disabled')).toBe('true')
		expect(el?.getAttribute('aria-label')).toBe('save, saving in progress')
	})

	it('swallows the click that would submit while inert', () => {
		let clicks = 0
		const { container } = render(ModalSaveButton, {
			props: { dirty: false, onclick: () => (clicks += 1) },
		})
		const el = button(container)
		const event = new MouseEvent('click', { bubbles: true, cancelable: true })
		el?.dispatchEvent(event)

		expect(clicks).toBe(0)
		expect(event.defaultPrevented).toBe(true)
	})

	it('runs its handler when enabled', () => {
		let clicks = 0
		const { container } = render(ModalSaveButton, {
			props: { dirty: true, onclick: () => (clicks += 1) },
		})
		const event = new MouseEvent('click', { bubbles: true, cancelable: true })
		button(container)?.dispatchEvent(event)

		expect(clicks).toBe(1)
		expect(event.defaultPrevented).toBe(false)
	})
})

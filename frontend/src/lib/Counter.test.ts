import { render, screen } from '@testing-library/svelte'
import { describe, expect, it } from 'vitest'
import Counter from './Counter.svelte'

describe('Counter', () => {
    it('renders with initial count of 0', () => {
        render(Counter)
        expect(screen.getByRole('button')).toHaveTextContent('Count is 0')
    })

    it('increments count when button is clicked', async () => {
        render(Counter)
        const button = screen.getByRole('button')

        expect(button).toHaveTextContent('Count is 0')

        await button.click()
        expect(button).toHaveTextContent('Count is 1')

        await button.click()
        expect(button).toHaveTextContent('Count is 2')
    })

    it('displays helper text', () => {
        render(Counter)
        expect(screen.getByText('Click the button to increment')).toBeInTheDocument()
    })
})

import { describe, expect, it } from 'vitest'

// Example API client test
describe('API Client', () => {
    it('can construct API URLs', () => {
        const baseUrl = 'http://localhost:8000'
        const endpoint = '/v1/users'
        const fullUrl = `${baseUrl}${endpoint}`

        expect(fullUrl).toBe('http://localhost:8000/v1/users')
    })

    it('can handle query parameters', () => {
        const params = new URLSearchParams({ page: '1', limit: '10' })
        const url = `/v1/users?${params.toString()}`

        expect(url).toBe('/v1/users?page=1&limit=10')
    })
})

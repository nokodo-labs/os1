export function createOnceCallback(callback?: () => void) {
	let called = false
	return () => {
		if (called) return
		called = true
		callback?.()
	}
}

// TypeID generator (UUIDv7-based, spec v0.3.0)
// produces identifiers like "thread_01h5fskfsk4fpeqwnsyz5hj55t"

const BASE32_ALPHABET = '0123456789abcdefghjkmnpqrstvwxyz'

function uuidv7Bytes(): Uint8Array {
	const ms = Date.now()
	const rand = crypto.getRandomValues(new Uint8Array(10))

	const bytes = new Uint8Array(16)
	// 48-bit unix epoch ms (big-endian)
	bytes[0] = (ms / 2 ** 40) & 0xff
	bytes[1] = (ms / 2 ** 32) & 0xff
	bytes[2] = (ms / 2 ** 24) & 0xff
	bytes[3] = (ms / 2 ** 16) & 0xff
	bytes[4] = (ms / 2 ** 8) & 0xff
	bytes[5] = ms & 0xff
	// version 7 + 12 bits rand_a
	bytes[6] = 0x70 | (rand[0] & 0x0f)
	bytes[7] = rand[1]
	// variant 10 + 62 bits rand_b
	bytes[8] = 0x80 | (rand[2] & 0x3f)
	bytes[9] = rand[3]
	bytes[10] = rand[4]
	bytes[11] = rand[5]
	bytes[12] = rand[6]
	bytes[13] = rand[7]
	bytes[14] = rand[8]
	bytes[15] = rand[9]

	return bytes
}

function encodeBase32Suffix(uuidBytes: Uint8Array): string {
	// treat 128-bit UUID as a big integer and encode as 26 base32 chars
	// each char encodes 5 bits, 26 chars = 130 bits (2 leading zero bits)
	let bigint = 0n
	for (const b of uuidBytes) {
		bigint = (bigint << 8n) | BigInt(b)
	}

	const chars: string[] = new Array(26)
	for (let i = 25; i >= 0; i--) {
		chars[i] = BASE32_ALPHABET[Number(bigint & 0x1fn)]
		bigint >>= 5n
	}
	return chars.join('')
}

export function newTypeid(prefix: string): string {
	const suffix = encodeBase32Suffix(uuidv7Bytes())
	return prefix ? `${prefix}_${suffix}` : suffix
}

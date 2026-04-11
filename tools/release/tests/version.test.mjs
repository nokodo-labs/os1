// tests for version computation logic.
// uses node:test built-in runner (Node 24+).

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import semver from "semver";

// -- inline computeNextRC / computeNextStable to test without git deps --
// these mirror the logic in release.mjs but are self-contained.

const PRERELEASE_ID = "rc";

function computeNextRC(currentVersion, bumpType, stableVersion = "0.0.0") {
	if (!currentVersion) {
		return `0.0.1-${PRERELEASE_ID}.0`;
	}

	const pre = semver.prerelease(currentVersion);

	if (pre && pre[0] === PRERELEASE_ID) {
		const currentBase = `${semver.major(currentVersion)}.${semver.minor(currentVersion)}.${semver.patch(currentVersion)}`;
		const escalatedBase = semver.inc(stableVersion, bumpType);

		if (semver.gt(escalatedBase, currentBase)) {
			return `${escalatedBase}-${PRERELEASE_ID}.0`;
		}

		return semver.inc(currentVersion, "prerelease", PRERELEASE_ID);
	}

	const newBase = semver.inc(currentVersion, bumpType);
	return `${newBase}-${PRERELEASE_ID}.0`;
}

function computeNextStable(currentVersion, bumpType) {
	if (!currentVersion) {
		return "0.0.1";
	}

	const pre = semver.prerelease(currentVersion);

	if (pre) {
		return `${semver.major(currentVersion)}.${semver.minor(currentVersion)}.${semver.patch(currentVersion)}`;
	}

	return semver.inc(currentVersion, bumpType);
}

// -- tests --

describe("computeNextRC", () => {
	it("should start at 0.0.1-rc.0 when no current version", () => {
		assert.equal(computeNextRC(null, "patch"), "0.0.1-rc.0");
	});

	it("should start at 0.0.1-rc.0 when no current version (minor bump)", () => {
		assert.equal(computeNextRC(null, "minor"), "0.0.1-rc.0");
	});

	it("should increment RC number for same bump level", () => {
		assert.equal(
			computeNextRC("0.1.0-rc.0", "patch", "0.0.1"),
			"0.1.0-rc.1",
		);
	});

	it("should increment RC number for minor when already at minor base", () => {
		assert.equal(
			computeNextRC("0.1.0-rc.2", "minor", "0.0.1"),
			"0.1.0-rc.3",
		);
	});

	it("should escalate base when bump type exceeds current RC base", () => {
		// current RC is 0.0.2-rc.0 (patch), but new commits have feat (minor)
		assert.equal(
			computeNextRC("0.0.2-rc.0", "minor", "0.0.1"),
			"0.1.0-rc.0",
		);
	});

	it("should escalate to major when breaking change on minor RC", () => {
		assert.equal(
			computeNextRC("0.1.0-rc.3", "major", "0.0.1"),
			"1.0.0-rc.0",
		);
	});

	it("should not regress when bump type is lower than current base", () => {
		// current RC is 0.1.0-rc.1, but new commits only have fix (patch)
		// stable is 0.0.1, so inc("0.0.1", "patch") = "0.0.2" < "0.1.0"
		// should just increment RC
		assert.equal(
			computeNextRC("0.1.0-rc.1", "patch", "0.0.1"),
			"0.1.0-rc.2",
		);
	});

	it("should start new RC from stable version bump", () => {
		assert.equal(computeNextRC("1.0.0", "minor"), "1.1.0-rc.0");
	});

	it("should start new RC from stable with major bump", () => {
		assert.equal(computeNextRC("1.2.3", "major"), "2.0.0-rc.0");
	});

	it("should handle first RC after a stable release", () => {
		assert.equal(computeNextRC("0.0.1", "patch"), "0.0.2-rc.0");
	});
});

describe("computeNextStable", () => {
	it("should return 0.0.1 when no current version", () => {
		assert.equal(computeNextStable(null, "patch"), "0.0.1");
	});

	it("should strip prerelease from RC version", () => {
		assert.equal(computeNextStable("0.2.0-rc.3", "patch"), "0.2.0");
	});

	it("should strip prerelease from higher RC", () => {
		assert.equal(computeNextStable("1.0.0-rc.0", "minor"), "1.0.0");
	});

	it("should bump stable version normally", () => {
		assert.equal(computeNextStable("1.0.0", "minor"), "1.1.0");
	});

	it("should bump patch on stable", () => {
		assert.equal(computeNextStable("1.2.3", "patch"), "1.2.4");
	});

	it("should bump major on stable", () => {
		assert.equal(computeNextStable("1.2.3", "major"), "2.0.0");
	});
});

describe("version validation", () => {
	it("should produce valid semver from computeNextRC", () => {
		const v = computeNextRC("0.1.0-rc.0", "minor", "0.0.1");
		assert.ok(semver.valid(v), `expected valid semver, got: ${v}`);
	});

	it("should produce valid semver from computeNextStable", () => {
		const v = computeNextStable("0.2.0-rc.3", "patch");
		assert.ok(semver.valid(v), `expected valid semver, got: ${v}`);
	});

	it("should always produce versions greater than input for RC", () => {
		const current = "0.1.0-rc.5";
		const next = computeNextRC(current, "patch", "0.0.1");
		assert.ok(semver.gt(next, current), `expected ${next} > ${current}`);
	});

	it("should ensure stable >= RC base", () => {
		const rc = "0.2.0-rc.3";
		const stable = computeNextStable(rc, "patch");
		// stable should equal the base of the RC
		assert.equal(stable, "0.2.0");
		assert.ok(semver.gte(stable, "0.2.0"));
	});
});

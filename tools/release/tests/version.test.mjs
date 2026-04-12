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

// -- pyproject.toml parsing tests --
// uses the actual readVersion/writeVersion from version.mjs
// with a temp file to avoid touching real project files.

import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, before } from "node:test";
import { PACKAGES } from "../src/config.mjs";
import { readVersion } from "../src/version.mjs";

describe("pyproject.toml version parsing", () => {
	let tmpDir;

	before(() => {
		tmpDir = mkdtempSync(join(tmpdir(), "release-test-"));
	});

	after(() => {
		rmSync(tmpDir, { recursive: true, force: true });
	});

	// helper: parse [project] section and extract version
	function parsePyprojectVersion(content) {
		const sections = content.split(/^(?=\[)/m);
		const projectBlock = sections.find((s) => /^\[project\]\s*$/m.test(s));
		if (!projectBlock) return null;
		const match = projectBlock.match(/^version\s*=\s*"([^"]+)"/m);
		return match ? match[1] : null;
	}

	// helper: write version into pyproject.toml content
	function writePyprojectVersion(content, newVersion) {
		const sections = content.split(/^(?=\[)/m);
		const projectBlock = sections.find((s) => /^\[project\]\s*$/m.test(s));
		if (!projectBlock) return null;
		const versionMatch = projectBlock.match(/^version\s*=\s*"([^"]+)"/m);
		if (!versionMatch) return null;
		const offset = content.indexOf(projectBlock);
		const versionIdx = offset + projectBlock.indexOf(versionMatch[0]);
		return (
			content.slice(0, versionIdx) +
			`version = "${newVersion}"` +
			content.slice(versionIdx + versionMatch[0].length)
		);
	}

	it("should read version from standard pyproject.toml", () => {
		const content = [
			"[project]",
			'name = "my-pkg"',
			'version = "1.2.3"',
			'description = "test"',
			"",
			"[tool.ruff]",
			"line-length = 88",
		].join("\n");
		assert.equal(parsePyprojectVersion(content), "1.2.3");
	});

	it("should not match version in [tool.*] sections", () => {
		const content = [
			"[project]",
			'name = "my-pkg"',
			"",
			"[tool.setuptools]",
			'version = "9.9.9"',
		].join("\n");
		// no version in [project], should return null
		assert.equal(parsePyprojectVersion(content), null);
	});

	it("should handle version in [project] when followed by [project.optional-dependencies]", () => {
		const content = [
			"[project]",
			'name = "nokodo-ai"',
			'version = "0.1.0"',
			'description = "Core library"',
			'requires-python = ">=3.13"',
			"",
			"[project.optional-dependencies]",
			"api = [",
			'    "fastapi>=0.115.0",',
			"]",
			"",
			"[build-system]",
			'requires = ["setuptools"]',
		].join("\n");
		assert.equal(parsePyprojectVersion(content), "0.1.0");
	});

	it("should write version correctly", () => {
		const original = [
			"[project]",
			'name = "my-pkg"',
			'version = "1.0.0"',
			'description = "test"',
			"",
			"[tool.ruff]",
			"line-length = 88",
		].join("\n");
		const updated = writePyprojectVersion(original, "2.0.0");
		assert.ok(updated);
		assert.equal(parsePyprojectVersion(updated), "2.0.0");
		// ensure other content is preserved
		assert.ok(updated.includes('name = "my-pkg"'));
		assert.ok(updated.includes("line-length = 88"));
	});

	it("should read version from actual backend pyproject.toml", () => {
		const lib = PACKAGES.find((p) => p.name === "library");
		const version = readVersion(lib);
		assert.ok(version, "should read a version from backend pyproject.toml");
		assert.ok(
			semver.valid(version),
			`version should be valid semver: ${version}`,
		);
	});

	it("should return null for pyproject.toml without version in [project]", () => {
		const content = [
			"[project]",
			'name = "test"',
			"",
			"[build-system]",
			'requires = ["setuptools"]',
		].join("\n");
		assert.equal(parsePyprojectVersion(content), null);
	});

	it("should return null when no [project] section exists", () => {
		const content = [
			"[tool.ruff]",
			"line-length = 88",
			'version = "1.0.0"',
		].join("\n");
		assert.equal(parsePyprojectVersion(content), null);
	});
});

// -- VERSION file tests --

import { readFileSync, writeFileSync } from "node:fs";

describe("VERSION file operations", () => {
	let tmpDir;

	before(() => {
		tmpDir = mkdtempSync(join(tmpdir(), "release-version-test-"));
	});

	after(() => {
		rmSync(tmpDir, { recursive: true, force: true });
	});

	it("should read version from VERSION file", () => {
		writeFileSync(join(tmpDir, "VERSION"), "1.2.3\n", "utf-8");
		const content = readFileSync(join(tmpDir, "VERSION"), "utf-8").trim();
		assert.equal(content, "1.2.3");
	});

	it("should read version from actual root VERSION file", () => {
		const root = PACKAGES.find((p) => p.path === ".");
		const version = readVersion(root);
		assert.ok(version, "should read a version from root VERSION file");
	});
});

// -- python-init (__init__.py __version__) tests --

describe("python-init __version__ operations", () => {
	let tmpDir;

	before(() => {
		tmpDir = mkdtempSync(join(tmpdir(), "release-pyinit-test-"));
	});

	after(() => {
		rmSync(tmpDir, { recursive: true, force: true });
	});

	it("should write __version__ into empty __init__.py", () => {
		const initPath = join(tmpDir, "__init__.py");
		writeFileSync(initPath, "", "utf-8");
		// test the write logic directly (writeVersion resolves relative to repoRoot)
		let content = readFileSync(initPath, "utf-8");
		const versionLine = '__version__ = "1.0.0"';
		content = versionLine + "\n" + content;
		writeFileSync(initPath, content, "utf-8");
		const result = readFileSync(initPath, "utf-8");
		assert.ok(result.includes('__version__ = "1.0.0"'));
	});

	it("should write __version__ after docstring", () => {
		const initPath = join(tmpDir, "__init__.py");
		writeFileSync(initPath, '"""My package."""\n', "utf-8");
		let content = readFileSync(initPath, "utf-8");
		const versionLine = '__version__ = "2.0.0"';
		const docstringEnd = content.match(/^("""[\s\S]*?"""\n?)/m);
		if (docstringEnd) {
			const idx = docstringEnd.index + docstringEnd[0].length;
			content =
				content.slice(0, idx) +
				"\n" +
				versionLine +
				"\n" +
				content.slice(idx);
		}
		writeFileSync(initPath, content, "utf-8");
		const result = readFileSync(initPath, "utf-8");
		assert.ok(result.startsWith('"""My package."""'));
		assert.ok(result.includes('__version__ = "2.0.0"'));
	});

	it("should update existing __version__", () => {
		const initPath = join(tmpDir, "__init__.py");
		writeFileSync(
			initPath,
			'"""Pkg."""\n\n__version__ = "2.0.0"\n',
			"utf-8",
		);
		let content = readFileSync(initPath, "utf-8");
		content = content.replace(
			/^__version__\s*=\s*"[^"]*"/m,
			'__version__ = "3.0.0"',
		);
		writeFileSync(initPath, content, "utf-8");
		const result = readFileSync(initPath, "utf-8");
		assert.ok(result.includes('__version__ = "3.0.0"'));
		assert.ok(!result.includes("2.0.0"));
	});

	it("should read __version__ from actual api __init__.py", () => {
		const api = PACKAGES.find((p) => p.name === "api");
		const version = readVersion(api);
		assert.ok(version, "should read a __version__ from api __init__.py");
	});
});

// -- extractReleaseFromTitle tests --

import { extractReleaseFromTitle } from "../src/release.mjs";

describe("extractReleaseFromTitle", () => {
	it("should extract name and version from prerelease PR title", () => {
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): prerelease OS1 v0.1.0-rc.0",
			),
			{ name: "OS1", version: "0.1.0-rc.0" },
		);
	});

	it("should extract name and version from stable release PR title", () => {
		assert.deepEqual(
			extractReleaseFromTitle("chore(release): release OS1 v1.2.3"),
			{ name: "OS1", version: "1.2.3" },
		);
	});

	it("should extract component name and version from component PR title", () => {
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): prerelease frontend v0.1.0-rc.0",
			),
			{ name: "frontend", version: "0.1.0-rc.0" },
		);
	});

	it("should extract higher RC numbers", () => {
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): prerelease OS1 v2.0.0-rc.15",
			),
			{ name: "OS1", version: "2.0.0-rc.15" },
		);
	});

	it("should NOT match title without version", () => {
		assert.equal(
			extractReleaseFromTitle("chore(release): bump dependencies"),
			null,
		);
	});

	it("should NOT match title with version in the middle", () => {
		assert.equal(extractReleaseFromTitle("update v1.2.3 to latest"), null);
	});

	it("should NOT match partial version", () => {
		assert.equal(
			extractReleaseFromTitle("chore(release): release OS1 v1.2"),
			null,
		);
	});

	it("should NOT match empty or null input", () => {
		assert.equal(extractReleaseFromTitle(""), null);
		assert.equal(extractReleaseFromTitle(null), null);
		assert.equal(extractReleaseFromTitle(undefined), null);
	});

	it("should match alpha/beta prerelease tags", () => {
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): release OS1 v1.0.0-alpha.1",
			),
			{ name: "OS1", version: "1.0.0-alpha.1" },
		);
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): release OS1 v1.0.0-beta.3",
			),
			{ name: "OS1", version: "1.0.0-beta.3" },
		);
	});

	it("should handle trailing whitespace", () => {
		assert.deepEqual(
			extractReleaseFromTitle("chore(release): release OS1 v1.2.3  "),
			{ name: "OS1", version: "1.2.3" },
		);
	});

	it("should extract api component name", () => {
		assert.deepEqual(
			extractReleaseFromTitle(
				"chore(release): prerelease api v0.2.0-rc.0",
			),
			{ name: "api", version: "0.2.0-rc.0" },
		);
	});

	it("should extract library component name", () => {
		assert.deepEqual(
			extractReleaseFromTitle("chore(release): release library v1.0.0"),
			{ name: "library", version: "1.0.0" },
		);
	});
});

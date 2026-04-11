// tests for config integrity and package definitions.
// uses node:test built-in runner (Node 24+).

import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import {
	BUMP_TYPES,
	CHANGELOG_SECTIONS,
	PACKAGES,
	PRERELEASE_ID,
	PRERELEASE_LABELS,
	RELEASE_LABELS,
	RELEASE_TAGGED_LABEL,
	SECTION_ORDER,
} from "../src/config.mjs";

const repoRoot = join(import.meta.dirname, "..", "..", "..");

describe("CHANGELOG_SECTIONS", () => {
	it("should have entries for all standard conventional commit types", () => {
		const types = CHANGELOG_SECTIONS.map((s) => s.type);
		for (const expected of [
			"feat",
			"fix",
			"perf",
			"refactor",
			"chore",
			"docs",
			"revert",
		]) {
			assert.ok(
				types.includes(expected),
				`missing section for type: ${expected}`,
			);
		}
	});

	it("should have each section referenced in SECTION_ORDER", () => {
		const sections = new Set(CHANGELOG_SECTIONS.map((s) => s.section));
		for (const section of sections) {
			assert.ok(
				SECTION_ORDER.includes(section),
				`section "${section}" not in SECTION_ORDER`,
			);
		}
	});

	it("should use lowercase section names (except emojis)", () => {
		for (const entry of CHANGELOG_SECTIONS) {
			// strip emoji prefix (first char + space) and check lowercase
			const text = entry.section.replace(/^[^\w]+/, "");
			assert.equal(
				text,
				text.toLowerCase(),
				`section "${entry.section}" should be lowercase`,
			);
		}
	});
});

describe("SECTION_ORDER", () => {
	it("should have no duplicates", () => {
		const unique = new Set(SECTION_ORDER);
		assert.equal(unique.size, SECTION_ORDER.length);
	});

	it("should start with new features", () => {
		assert.ok(SECTION_ORDER[0].includes("new features"));
	});

	it("should end with reverts", () => {
		assert.ok(SECTION_ORDER[SECTION_ORDER.length - 1].includes("reverts"));
	});
});

describe("PACKAGES", () => {
	it("should have a root package", () => {
		const root = PACKAGES.find((p) => p.path === ".");
		assert.ok(root, "root package (path='.') not found");
		assert.equal(root.name, "os1");
		assert.equal(root.componentTag, false);
	});

	it("should have unique package names", () => {
		const names = PACKAGES.map((p) => p.name);
		assert.equal(new Set(names).size, names.length);
	});

	it("should have unique package paths", () => {
		const paths = PACKAGES.map((p) => p.path);
		assert.equal(new Set(paths).size, paths.length);
	});

	it("should have valid releaseType values", () => {
		const valid = ["simple", "node", "python", "none"];
		for (const pkg of PACKAGES) {
			assert.ok(
				valid.includes(pkg.releaseType),
				`invalid releaseType "${pkg.releaseType}" for ${pkg.name}`,
			);
		}
	});

	it("should point to existing directories", () => {
		for (const pkg of PACKAGES) {
			const dir = pkg.path === "." ? repoRoot : join(repoRoot, pkg.path);
			assert.ok(
				existsSync(dir),
				`package path does not exist: ${pkg.path} (${dir})`,
			);
		}
	});

	it("should have version files for node/python packages", () => {
		for (const pkg of PACKAGES) {
			const dir = pkg.versionDir || pkg.path;
			const pkgPath = dir === "." ? repoRoot : join(repoRoot, dir);
			if (pkg.releaseType === "node") {
				assert.ok(
					existsSync(join(pkgPath, "package.json")),
					`missing package.json for ${pkg.name} at ${pkgPath}`,
				);
			} else if (pkg.releaseType === "python") {
				assert.ok(
					existsSync(join(pkgPath, "pyproject.toml")),
					`missing pyproject.toml for ${pkg.name} at ${pkgPath}`,
				);
			}
		}
	});

	it("should have componentTag=true for all non-root packages with tags", () => {
		const tagged = PACKAGES.filter((p) => p.path !== "." && p.componentTag);
		assert.ok(tagged.length >= 3, "should have at least 3 component tags");
	});

	it("should have library package pointing to backend/nokodo_ai", () => {
		const lib = PACKAGES.find((p) => p.name === "library");
		assert.ok(lib, "library package not found");
		assert.equal(lib.path, "backend/nokodo_ai");
		assert.equal(lib.versionDir, "backend");
		assert.equal(lib.releaseType, "python");
	});
});

describe("labels", () => {
	it("should have required base labels", () => {
		assert.ok(RELEASE_LABELS.includes("bot"));
		assert.ok(RELEASE_LABELS.includes("release"));
		assert.ok(RELEASE_LABELS.includes("release: pending"));
	});

	it("should have prerelease label in PRERELEASE_LABELS", () => {
		assert.ok(PRERELEASE_LABELS.includes("prerelease"));
		assert.ok(PRERELEASE_LABELS.includes("bot"));
		assert.ok(PRERELEASE_LABELS.includes("release"));
	});

	it("should have tagged label defined", () => {
		assert.equal(RELEASE_TAGGED_LABEL, "release: tagged");
	});
});

describe("constants", () => {
	it("should have rc as prerelease id", () => {
		assert.equal(PRERELEASE_ID, "rc");
	});

	it("should have standard bump types", () => {
		assert.ok(BUMP_TYPES.includes("feat"));
		assert.ok(BUMP_TYPES.includes("fix"));
		assert.ok(BUMP_TYPES.includes("perf"));
	});
});

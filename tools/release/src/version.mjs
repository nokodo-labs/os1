// version file operations - read/write version in package.json and pyproject.toml.

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { PACKAGES } from "./config.mjs";

// get the repo root directory (2 levels up from src/).
function repoRoot() {
	return join(import.meta.dirname, "..", "..", "..");
}

// read the current version from a package's version file.
export function readVersion(pkg) {
	const root = repoRoot();
	const pkgPath = pkg.path === "." ? root : join(root, pkg.path);

	if (pkg.releaseType === "node") {
		const pjPath = join(pkgPath, "package.json");
		const pj = JSON.parse(readFileSync(pjPath, "utf-8"));
		return pj.version;
	}

	if (pkg.releaseType === "python") {
		const tomlPath = join(pkgPath, "pyproject.toml");
		const content = readFileSync(tomlPath, "utf-8");
		// match version within [project] section, not arbitrary [tool.*] sections
		const projectSection = content.match(
			/^\[project\]\s*\n([\s\S]*?)(?=^\[(?!project\.)|$)/m,
		);
		if (!projectSection) return null;
		const match = projectSection[1].match(/^version\s*=\s*"([^"]+)"/m);
		return match ? match[1] : null;
	}

	// 'simple' or 'none' type - no version file, use git tags only
	return null;
}

// write a new version to a package's version file.
export function writeVersion(pkg, version) {
	const root = repoRoot();
	const pkgPath = pkg.path === "." ? root : join(root, pkg.path);

	if (pkg.releaseType === "node") {
		const pjPath = join(pkgPath, "package.json");
		const pj = JSON.parse(readFileSync(pjPath, "utf-8"));
		pj.version = version;
		writeFileSync(pjPath, JSON.stringify(pj, null, "\t") + "\n", "utf-8");
		return pjPath;
	}

	if (pkg.releaseType === "python") {
		const tomlPath = join(pkgPath, "pyproject.toml");
		let content = readFileSync(tomlPath, "utf-8");
		// match version within [project] section only
		const projectMatch = content.match(
			/^\[project\]\s*\n([\s\S]*?)(?=^\[(?!project\.)|$)/m,
		);
		if (!projectMatch) return null;
		const offset = content.indexOf(projectMatch[0]);
		const sectionContent = projectMatch[1];
		const versionMatch = sectionContent.match(/^version\s*=\s*"([^"]+)"/m);
		if (!versionMatch) return null;

		const versionIdx = offset + projectMatch[0].indexOf(versionMatch[0]);
		content =
			content.slice(0, versionIdx) +
			`version = "${version}"` +
			content.slice(versionIdx + versionMatch[0].length);
		writeFileSync(tomlPath, content, "utf-8");
		return tomlPath;
	}

	return null;
}

// update all packages to the given version. returns list of changed file paths.
export function updateAllVersions(version) {
	const changed = [];
	for (const pkg of PACKAGES) {
		const path = writeVersion(pkg, version);
		if (path) changed.push(path);
	}
	return changed;
}

// get paths of all version files (for git add).
export function getVersionFilePaths() {
	const root = repoRoot();
	const paths = [];
	for (const pkg of PACKAGES) {
		const pkgPath = pkg.path === "." ? root : join(root, pkg.path);
		if (pkg.releaseType === "node") {
			paths.push(join(pkgPath, "package.json"));
		} else if (pkg.releaseType === "python") {
			paths.push(join(pkgPath, "pyproject.toml"));
		}
	}
	return paths;
}

// version file operations - read/write version in package.json and pyproject.toml.

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

// get the repo root directory (2 levels up from src/).
function repoRoot() {
	return join(import.meta.dirname, "..", "..", "..");
}

// read the current version from a package's version file.
export function readVersion(pkg) {
	const root = repoRoot();
	const dir = pkg.versionDir || pkg.path;
	const pkgPath = dir === "." ? root : join(root, dir);

	if (pkg.releaseType === "node") {
		const pjPath = join(pkgPath, "package.json");
		const pj = JSON.parse(readFileSync(pjPath, "utf-8"));
		return pj.version;
	}

	if (pkg.releaseType === "python") {
		const tomlPath = join(pkgPath, "pyproject.toml");
		const content = readFileSync(tomlPath, "utf-8");
		// extract the [project] section: everything from [project] to the next
		// top-level section header (excluding [project.*] subsections).
		// split on section headers and grab the first block after [project].
		const sections = content.split(/^(?=\[)/m);
		const projectBlock = sections.find((s) => /^\[project\]\s*$/m.test(s));
		if (!projectBlock) return null;
		const match = projectBlock.match(/^version\s*=\s*"([^"]+)"/m);
		return match ? match[1] : null;
	}

	if (pkg.releaseType === "version") {
		const vPath = join(pkgPath, "VERSION");
		try {
			return readFileSync(vPath, "utf-8").trim() || null;
		} catch (err) {
			if (err?.code === "ENOENT") return null;
			throw err;
		}
	}

	if (pkg.releaseType === "python-init") {
		const initPath = join(pkgPath, "__init__.py");
		try {
			const content = readFileSync(initPath, "utf-8");
			const match = content.match(/^__version__\s*=\s*"([^"]+)"/m);
			return match ? match[1] : null;
		} catch (err) {
			if (err?.code === "ENOENT") return null;
			throw err;
		}
	}

	// 'simple' type - no version file, use git tags only
	return null;
}

// write a new version to a package's version file.
export function writeVersion(pkg, version) {
	const root = repoRoot();
	const dir = pkg.versionDir || pkg.path;
	const pkgPath = dir === "." ? root : join(root, dir);

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
		// find [project] section by splitting on section headers
		const sections = content.split(/^(?=\[)/m);
		const projectBlock = sections.find((s) => /^\[project\]\s*$/m.test(s));
		if (!projectBlock) return null;
		const versionMatch = projectBlock.match(/^version\s*=\s*"([^"]+)"/m);
		if (!versionMatch) return null;

		const offset = content.indexOf(projectBlock);
		const versionIdx = offset + projectBlock.indexOf(versionMatch[0]);
		content =
			content.slice(0, versionIdx) +
			`version = "${version}"` +
			content.slice(versionIdx + versionMatch[0].length);
		writeFileSync(tomlPath, content, "utf-8");
		return tomlPath;
	}

	if (pkg.releaseType === "version") {
		const vPath = join(pkgPath, "VERSION");
		writeFileSync(vPath, version + "\n", "utf-8");
		return vPath;
	}

	if (pkg.releaseType === "python-init") {
		const initPath = join(pkgPath, "__init__.py");
		let content;
		try {
			content = readFileSync(initPath, "utf-8");
		} catch (err) {
			if (err?.code === "ENOENT") content = "";
			else throw err;
		}
		const versionLine = `__version__ = "${version}"`;
		if (content.match(/^__version__\s*=\s*"[^"]*"/m)) {
			content = content.replace(
				/^__version__\s*=\s*"[^"]*"/m,
				versionLine,
			);
		} else {
			// prepend after docstring if present, otherwise at top
			const docstringEnd = content.match(/^("""[\s\S]*?"""\n?)/m);
			if (docstringEnd) {
				const idx = docstringEnd.index + docstringEnd[0].length;
				content =
					content.slice(0, idx) +
					"\n" +
					versionLine +
					"\n" +
					content.slice(idx);
			} else {
				content = versionLine + "\n" + content;
			}
		}
		writeFileSync(initPath, content, "utf-8");
		return initPath;
	}

	return null;
}

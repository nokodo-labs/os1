import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { readdir, readFile, stat } from "node:fs/promises";
import { relative, sep } from "node:path";
import { spawnSync } from "node:child_process";

const cwd = process.cwd();
const requireFromCwd = createRequire(`${cwd}${sep}package.json`);
const prettierBin = requireFromCwd.resolve("prettier/bin/prettier.cjs");
const ignoredDirs = new Set([
	".git",
	".svelte-kit",
	"build",
	"coverage",
	"dist",
	"node_modules",
	"test-results",
]);

async function snapshot(dir) {
	const files = await listFiles(dir);
	const entries = await Promise.all(
		files.map(async (file) => [file, await hashFile(file)]),
	);
	return new Map(entries);
}

async function listFiles(dir) {
	const entries = await readdir(dir, { withFileTypes: true });
	const files = [];
	for (const entry of entries) {
		const path = `${dir}${sep}${entry.name}`;
		if (entry.isDirectory()) {
			if (!ignoredDirs.has(entry.name))
				files.push(...(await listFiles(path)));
		} else if (entry.isFile()) {
			files.push(path);
		}
	}
	return files;
}

async function hashFile(path) {
	const info = await stat(path);
	if (!info.isFile()) return "";
	const content = await readFile(path);
	return createHash("sha1").update(content).digest("hex");
}

function changedFiles(before, after) {
	const changed = [];
	for (const [file, hash] of after) {
		if (before.get(file) !== hash)
			changed.push(relative(cwd, file).replaceAll(sep, "/"));
	}
	return changed.sort((a, b) => a.localeCompare(b));
}

const before = await snapshot(cwd);
const result = spawnSync(
	process.execPath,
	[prettierBin, "--write", ".", "--log-level", "silent"],
	{
		cwd,
		encoding: "utf8",
	},
);

if (result.status !== 0) {
	if (result.stdout.trim()) console.log(result.stdout.trim());
	if (result.stderr.trim()) console.error(result.stderr.trim());
	process.exit(result.status ?? 1);
}

const after = await snapshot(cwd);
const changed = changedFiles(before, after);
if (changed.length === 0) {
	console.log("format: no changes");
} else {
	console.log(
		`format: changed ${changed.length} ${changed.length === 1 ? "file" : "files"}`,
	);
	const maxListed = 25;
	for (const file of changed.slice(0, maxListed)) console.log(`- ${file}`);
	if (changed.length > maxListed)
		console.log(`- and ${changed.length - maxListed} more`);
}

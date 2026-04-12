// git operations - tag listing, commit log extraction.
// uses execFileSync with argument arrays to prevent shell injection.

import { execFileSync } from "node:child_process";
import semver from "semver";

function exec(cmd, args = [], opts = {}) {
	return execFileSync(cmd, args, { encoding: "utf-8", ...opts }).trim();
}

// ref name validation - prevents injection via crafted ref names.
const SAFE_REF = /^[a-zA-Z0-9._\-/^~]+$/;
function assertSafeRef(ref) {
	if (ref && !SAFE_REF.test(ref)) {
		throw new Error(`invalid git ref: ${ref}`);
	}
}

// get all semver tags sorted descending by semver (not git sort).
export function getSemverTags() {
	let raw;
	try {
		raw = exec("git", ["tag", "--list", "v*"]);
	} catch (err) {
		if (err?.status !== 1) throw err;
		return [];
	}
	if (!raw) return [];

	return raw
		.split("\n")
		.map((t) => t.trim())
		.filter((t) => semver.valid(t))
		.sort((a, b) => semver.rcompare(a, b));
}

// get the latest semver tag reachable from the current HEAD.
export function getLatestTag() {
	const tags = getSemverTags();
	if (tags.length === 0) return null;

	// find tags that are ancestors of HEAD
	for (const tag of tags) {
		try {
			exec("git", ["merge-base", "--is-ancestor", tag, "HEAD"]);
			return tag;
		} catch (err) {
			// exit 1 = not an ancestor, try next tag
			if (err?.status !== 1) throw err;
		}
	}
	return null;
}

// get raw commit messages between two refs (exclusive from, inclusive to).
// returns array of { hash, message, author } objects.
// paths: optional array of file/dir paths to restrict commits to.
export function getCommits(from, to = "HEAD", paths = []) {
	assertSafeRef(from);
	assertSafeRef(to);
	const range = from ? `${from}..${to}` : to;
	const SEP = "---COMMIT_SEP---";
	const REC = "---COMMIT_REC---";
	let raw;
	try {
		const args = [
			"log",
			range,
			`--format=%H${SEP}%aN${SEP}%B${REC}`,
			"--no-merges",
		];
		if (paths.length > 0)
			args.push("--", ...paths.map((p) => `:(top)${p}`));
		raw = exec("git", args);
	} catch (err) {
		// exit 128 = bad ref (e.g. tag doesn't exist yet), exit 1 = empty range
		if (err?.status !== 1 && err?.status !== 128) throw err;
		return [];
	}
	if (!raw) return [];

	return raw
		.split(REC)
		.map((block) => block.trim())
		.filter(Boolean)
		.map((block) => {
			const firstSep = block.indexOf(SEP);
			const secondSep = block.indexOf(SEP, firstSep + SEP.length);
			const hash = block.slice(0, firstSep).trim();
			const author = block.slice(firstSep + SEP.length, secondSep).trim();
			const message = block.slice(secondSep + SEP.length).trim();
			return { hash, author, message };
		})
		.filter((c) => c.hash && c.message);
}

// get the short hash.
export function shortHash(hash) {
	return hash.slice(0, 7);
}

// check if a tag already exists.
export function tagExists(tag) {
	assertSafeRef(tag);
	try {
		exec("git", ["rev-parse", "--verify", `refs/tags/${tag}`]);
		return true;
	} catch (err) {
		// exit 1/128 = ref doesn't exist
		if (err?.status !== 1 && err?.status !== 128) throw err;
		return false;
	}
}

// get the highest semver tag across the entire repo (any branch).
// used to prevent version regression when branches diverge.
export function getHighestTag() {
	const tags = getSemverTags();
	return tags.length > 0 ? tags[0] : null;
}

// get all semver tags for a component, sorted descending by semver.
// component tags follow the pattern "{name}-v{version}".
export function getComponentSemverTags(name) {
	const prefix = `${name}-v`;
	let raw;
	try {
		raw = exec("git", ["tag", "--list", `${prefix}*`]);
	} catch (err) {
		if (err?.status !== 1) throw err;
		return [];
	}
	if (!raw) return [];

	return raw
		.split("\n")
		.map((t) => t.trim())
		.filter((t) => {
			const ver = t.startsWith(prefix) ? t.slice(prefix.length) : null;
			return ver && semver.valid(ver);
		})
		.sort((a, b) => {
			const va = a.slice(prefix.length);
			const vb = b.slice(prefix.length);
			return semver.rcompare(va, vb);
		});
}

// get the latest component tag reachable from HEAD.
// returns the full tag string (e.g., "api-v0.1.0-rc.0") or null.
export function getLatestComponentTag(name) {
	const tags = getComponentSemverTags(name);
	for (const tag of tags) {
		try {
			exec("git", ["merge-base", "--is-ancestor", tag, "HEAD"]);
			return tag;
		} catch (err) {
			// exit 1 = not an ancestor, try next tag
			if (err?.status !== 1) throw err;
		}
	}
	return null;
}

// get the repo owner/name from git remote.
export function getRepoSlug() {
	const url = exec("git", ["remote", "get-url", "origin"]);
	// handle both HTTPS and SSH URLs (including custom host aliases like github.com-*)
	const match = url.match(/github\.com[^:/]*[:/](.+?)(?:\.git)?$/);
	return match ? match[1] : null;
}

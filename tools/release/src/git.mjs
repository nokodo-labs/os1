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
	} catch {
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
		} catch {
			// tag is not an ancestor of HEAD, try next
		}
	}
	return null;
}

// get the latest tag on a specific branch (any tag, not just ancestors of HEAD).
export function getLatestTagOnBranch(branch) {
	assertSafeRef(branch);
	const tags = getSemverTags();
	if (tags.length === 0) return null;

	for (const tag of tags) {
		try {
			exec("git", ["merge-base", "--is-ancestor", tag, branch]);
			return tag;
		} catch {
			continue;
		}
	}
	return null;
}

// get raw commit messages between two refs (exclusive from, inclusive to).
// returns array of { hash, message } objects.
export function getCommits(from, to = "HEAD") {
	assertSafeRef(from);
	assertSafeRef(to);
	const range = from ? `${from}..${to}` : to;
	const SEP = "---COMMIT_SEP---";
	let raw;
	try {
		raw = exec("git", [
			"log",
			range,
			`--format=%H${SEP}%B${SEP}${SEP}`,
			"--no-merges",
		]);
	} catch {
		return [];
	}
	if (!raw) return [];

	return raw
		.split(`${SEP}${SEP}`)
		.map((block) => block.trim())
		.filter(Boolean)
		.map((block) => {
			const sepIdx = block.indexOf(SEP);
			const hash = block.slice(0, sepIdx).trim();
			const message = block.slice(sepIdx + SEP.length).trim();
			return { hash, message };
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
	} catch {
		return false;
	}
}

// get the highest semver tag across the entire repo (any branch).
// used to prevent version regression when branches diverge.
export function getHighestTag() {
	const tags = getSemverTags();
	return tags.length > 0 ? tags[0] : null;
}

// get the repo owner/name from git remote.
export function getRepoSlug() {
	const url = exec("git", ["remote", "get-url", "origin"]);
	// handle both HTTPS and SSH URLs (including custom host aliases like github.com-*)
	const match = url.match(/github\.com[^:/]*[:/](.+?)(?:\.git)?$/);
	return match ? match[1] : null;
}

// get commit count between two refs.
export function getCommitCount(from, to = "HEAD") {
	assertSafeRef(from);
	assertSafeRef(to);
	const range = from ? `${from}..${to}` : to;
	try {
		return parseInt(exec("git", ["rev-list", "--count", range]), 10);
	} catch {
		return 0;
	}
}

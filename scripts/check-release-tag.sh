#!/usr/bin/env bash
# Refuse to deploy a commit that is not a tagged release. VERSION.md says every
# deploy bumps the beta number and gets a tag; the deploy workflow runs this
# against the pushed commit so an untagged push to main never reaches the live
# site. Usage: scripts/check-release-tag.sh [commit]   (default: HEAD)
set -euo pipefail

sha="${1:-$(git rev-parse HEAD)}"
version="$(head -n 1 VERSION.md | tr -d '[:space:]')"
tag="v$version"
roadmap="$(sed -n 's/^Active release: *//p' VERSION.md | tr -d '[:space:]')"

hint_tag="$tag"
fail() {
  echo "::error::$1"
  echo "To release: bump the first line of VERSION.md, add the Releases row in $roadmap, commit, then:"
  echo "  git tag -a $hint_tag -m \"$hint_tag\" && git push --atomic origin main $hint_tag"
  exit 1
}

[ -n "$version" ] || fail "VERSION.md has no version on its first line."
[ -f "$roadmap" ] || fail "VERSION.md names an active release roadmap that does not exist: $roadmap"

# The runner's checkout is shallow and has no tags; fetch just this one. A miss
# is reported below, not here.
if ! git rev-parse -q --verify "refs/tags/$tag^{commit}" >/dev/null 2>&1; then
  git fetch -q --no-tags --depth 1 origin "refs/tags/$tag:refs/tags/$tag" 2>/dev/null || true
fi
tagged="$(git rev-parse -q --verify "refs/tags/$tag^{commit}" 2>/dev/null || true)"

[ -n "$tagged" ] || fail "No tag $tag exists for the version in VERSION.md ($version)."
[ "$tagged" = "$sha" ] || { hint_tag="v<new version>"; fail "Tag $tag points at ${tagged:0:7}, not at the commit being deployed (${sha:0:7}): VERSION.md was not bumped for this push."; }
grep -qF "| \`$version\` |" "$roadmap" || fail "$roadmap has no Releases row for $version."

echo "release check: $tag is at ${sha:0:7} and $roadmap has its Releases row"

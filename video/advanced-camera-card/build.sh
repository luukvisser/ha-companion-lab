#!/bin/bash
# build.sh <card checkout> <name>: builds the Advanced Camera Card from a checkout (a worktree per PR
# branch works well) and puts its dist/ in $BUILDS_DIR/<name>, with BUILD-INFO: the commit, the
# branch, whether the tree had uncommitted changes, and the time. One build per PR, measured on its
# own, instead of a combined build (`lab card ... <name>` then installs and measures it).
#
# Builds in a container (Node 22, Yarn 4.9.1 through corepack, as the card's Volta pins), at low
# priority. The checkout's node_modules is used when present (it may be a symlink to another
# checkout's); otherwise `yarn install --immutable` runs first, which downloads the dependencies.
set -euo pipefail
. "$(dirname "$0")/../../lib.sh"
src=$(cd "${1:?usage: build.sh <card checkout> <name>}" && pwd)
name=${2:?give the build a name (a folder under \$BUILDS_DIR)}
[[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "the name may only hold letters, digits, . _ -" >&2; exit 1; }
[ -f "$src/package.json" ] || { echo "$src is not a card checkout (no package.json)" >&2; exit 1; }
# A node_modules symlink pointing outside the checkout is mounted at the same relative place.
mounts=(-v "$src:/w/card")
if [ -L "$src/node_modules" ]; then
  nm=$(cd "$src" && cd "$(readlink node_modules)" && pwd)
  mounts+=(-v "$nm:/w/card/node_modules")
fi
nice -n 19 docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -e COREPACK_ENABLE_DOWNLOAD_PROMPT=0 \
  -e COREPACK_HOME=/tmp/corepack "${mounts[@]}" -w /w/card \
  node:22-alpine@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202 \
  sh -c '[ -d node_modules ] || corepack yarn@4.9.1 install --immutable; rm -rf dist && corepack yarn@4.9.1 run build >/dev/null'
dest="$BUILDS_DIR/$name"
rm -rf "$dest"
mkdir -p "$BUILDS_DIR"
cp -r "$src/dist" "$dest"
{
  echo "commit $(git -C "$src" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "branch $(git -C "$src" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "uncommitted $([ -n "$(git -C "$src" status --porcelain --untracked-files=no 2>/dev/null)" ] && echo yes || echo no)"
  echo "built $(date -u +%FT%TZ)"
} >"$dest/BUILD-INFO"
echo "built $name: $(tr '\n' ' ' <"$dest/BUILD-INFO")"

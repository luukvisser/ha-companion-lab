#!/bin/bash
# checks.sh: every check CI runs on a pull request (.github/workflows/checks.yml), in pinned
# containers, so it runs the same locally and in CI. Needs only Docker (and network for the
# external links of the link check; LINKS=offline skips those).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ROOT=$(pwd)

SHELLCHECK_IMAGE=koalaman/shellcheck:v0.11.0@sha256:61862eba1fcf09a484ebcc6feea46f1782532571a34ed51fedf90dd25f925a8d
BASH32_IMAGE=bash:3.2@sha256:2556c2da19c32c1614d318645c73a7bf64d38be21cf69e98e3ca51f053983719
BASH5_IMAGE=bash:5.2@sha256:2cf7ddaf5f6369c16a0359e3bd48e54ada211a2e4e90d87532ad2958d642bdd5
NODE_IMAGE=node:22-alpine@sha256:0e1754758c2df4cfa3e68d59e2e1b7374bb7fd9ea6328eaaacf15cc934af8202
PY_IMAGE=python:3.13-alpine@sha256:1e1f6334529d1fb26a2ef619d7cffb30a7c7d7cc1cc7338ebee283a58d1aeaca
LYCHEE_IMAGE=lycheeverse/lychee:0.24.2-alpine@sha256:2255c0b916cc8fc4193f59a4549358a6bae0f7d4ea16b5e1dd4c3b2733c35504
# yamllint and its dependencies: tools/requirements-yamllint.txt (versions and wheel hashes).

failed=0
# Addresses that only exist while the lab runs (loopback, the emulator, a devcontainer).
LOCAL_URLS=(--exclude '^https?://(127\.0\.0\.1|localhost|10\.0\.2\.2|host\.docker\.internal)')
run() { # run <name> <command...>
  printf '== %s\n' "$1"; shift
  if "$@"; then echo "   ok"; else echo "   FAILED"; failed=$((failed + 1)); fi
}
d() { docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$ROOT:/r:ro" -w /r "$@"; }

mapfile -t SH < <(git ls-files -co --exclude-standard '*.sh' 2>/dev/null || find . -name '*.sh' -not -path './.git/*')
mapfile -t PY < <(git ls-files -co --exclude-standard '*.py' 2>/dev/null || find . -name '*.py' -not -path './.git/*')
mapfile -t JS < <(git ls-files -co --exclude-standard '*.js' 2>/dev/null || find . -name '*.js' -not -path './.git/*')
mapfile -t YML < <(git ls-files -co --exclude-standard '*.yml' '*.yaml' 2>/dev/null || find . \( -name '*.yml' -o -name '*.yaml' \) -not -path './.git/*')

run "shellcheck" d "$SHELLCHECK_IMAGE" --severity=warning -x "${SH[@]}"
run "bash -n (bash 5)" d --entrypoint bash "$BASH5_IMAGE" -c 'for f in "$@"; do bash -n "$f" || exit 1; done' _ "${SH[@]}"
run "bash -n (bash 3.2, macOS)" d --entrypoint bash "$BASH32_IMAGE" -c 'for f in "$@"; do bash -n "$f" || exit 1; done' _ "${SH[@]}"
run "python compile" d "$PY_IMAGE" python -c 'import sys,ast; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]' "${PY[@]}"
run "python self-tests" d "$PY_IMAGE" sh -c 'python -I video/advanced-camera-card/tools/bg_summary.py --self-test >/dev/null && python -I video/advanced-camera-card/tools/rate_frames.py --self-test && python -I video/tools/go2rtc-consumers.py --self-test && python -I stack/sim_talk.py --self-test'
run "node --check" d "$NODE_IMAGE" sh -c 'for f in "$@"; do node --check "$f" || exit 1; done' _ "${JS[@]}"
run "yamllint" d "$PY_IMAGE" sh -c "pip install -q --no-cache-dir --require-hashes --no-deps --target /tmp/yl -r tools/requirements-yamllint.txt >/dev/null 2>&1 && PYTHONPATH=/tmp/yl python -m yamllint -d '{extends: relaxed, rules: {line-length: {max: 130}}}' \"\$@\"" _ "${YML[@]}"
run "house data" d "$PY_IMAGE" python -I tools/check-house-data.py /r
# AGENTS.md (other agents) and the Claude Code skill must carry the same hard rules.
hard_rules() { awk '/^## Hard rules$/{on=1} on && /^## / && !/^## Hard rules$/{exit} on' "$1"; }
same_hard_rules() {
  local a b
  a=$(hard_rules AGENTS.md); b=$(hard_rules .claude/skills/ha-companion-lab/SKILL.md)
  [ -n "$a" ] && [ "$a" = "$b" ] || { echo "   the Hard rules in AGENTS.md and SKILL.md differ"; return 1; }
}
run "hard rules in step" same_hard_rules
if [ "${LINKS:-}" = offline ]; then
  run "links (offline)" d "$LYCHEE_IMAGE" --offline --no-progress --include-fragments "${LOCAL_URLS[@]}" '*.md' '**/*.md'
else
  run "links" d "$LYCHEE_IMAGE" --no-progress --max-concurrency 4 --include-fragments "${LOCAL_URLS[@]}" '*.md' '**/*.md'
fi

echo
[ "$failed" -eq 0 ] && echo "all checks passed" || { echo "$failed check(s) failed"; exit 1; }

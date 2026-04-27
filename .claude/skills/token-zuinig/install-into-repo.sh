#!/usr/bin/env bash
# install-token-zuinig.sh — kopieer de token-zuinig skill naar een of meer repos
# Gebruik:
#   ./install-token-zuinig.sh <repo-path> [<repo-path> ...]
#   ./install-token-zuinig.sh --all                       # alle repos uit ~/.token-zuinig-targets
#   ./install-token-zuinig.sh --commit <repo-path> ...    # ook git add + commit (geen push)
#
# Bron: ~/.claude/skills/token-zuinig/SKILL.md (user-level install).
# Doel: <repo>/.claude/skills/token-zuinig/SKILL.md

set -euo pipefail

SRC="${TOKEN_ZUINIG_SRC:-$HOME/.claude/skills/token-zuinig/SKILL.md}"
TARGETS_FILE="$HOME/.token-zuinig-targets"
DO_COMMIT=0
TARGETS=()

if [[ ! -f "$SRC" ]]; then
  echo "Bron ontbreekt: $SRC" >&2
  echo "Installeer eerst de skill op user-level, of zet TOKEN_ZUINIG_SRC." >&2
  exit 1
fi

while (( $# )); do
  case "$1" in
    --commit) DO_COMMIT=1; shift ;;
    --all)
      [[ -f "$TARGETS_FILE" ]] || { echo "Geen $TARGETS_FILE" >&2; exit 1; }
      while IFS= read -r line; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        TARGETS+=("$line")
      done < "$TARGETS_FILE"
      shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done

(( ${#TARGETS[@]} )) || { echo "Geen repos opgegeven." >&2; exit 1; }

for repo in "${TARGETS[@]}"; do
  repo="${repo/#~/$HOME}"
  if [[ ! -d "$repo/.git" ]]; then
    echo "  skip $repo (geen git repo)"
    continue
  fi

  dst="$repo/.claude/skills/token-zuinig/SKILL.md"
  mkdir -p "$(dirname "$dst")"

  if [[ -f "$dst" ]] && cmp -s "$SRC" "$dst"; then
    echo "  ok   $repo (al up-to-date)"
    continue
  fi

  cp "$SRC" "$dst"
  echo "  copy $repo"

  if (( DO_COMMIT )); then
    git -C "$repo" add .claude/skills/token-zuinig/SKILL.md
    if git -C "$repo" diff --cached --quiet; then
      echo "       niets te committen"
    else
      git -C "$repo" commit -m "Add token-zuinig skill" >/dev/null
      echo "       committed"
    fi
  fi
done

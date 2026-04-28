#!/usr/bin/env bash
# install-token-zuinig.sh — kopieer de token-zuinig skill naar een of meer repos
# Gebruik:
#   ./install-token-zuinig.sh <repo-path> [<repo-path> ...]
#   ./install-token-zuinig.sh --all                          # alle repos uit ~/.token-zuinig-targets
#   ./install-token-zuinig.sh --commit <repo-path> ...       # ook git add + commit (geen push)
#   ./install-token-zuinig.sh --update-and-push --all        # commit + push huidige branch per repo
#   ./install-token-zuinig.sh --update-and-push --allow-main ...  # sta push naar main/master toe
#
# Bron: ~/.claude/skills/token-zuinig/SKILL.md (user-level install).
# Doel: <repo>/.claude/skills/token-zuinig/SKILL.md

set -euo pipefail

SRC="${TOKEN_ZUINIG_SRC:-$HOME/.claude/skills/token-zuinig/SKILL.md}"
TARGETS_FILE="$HOME/.token-zuinig-targets"
DO_COMMIT=0
DO_PUSH=0
ALLOW_MAIN=0
TARGETS=()

if [[ ! -f "$SRC" ]]; then
  echo "Bron ontbreekt: $SRC" >&2
  echo "Installeer eerst de skill op user-level, of zet TOKEN_ZUINIG_SRC." >&2
  exit 1
fi

while (( $# )); do
  case "$1" in
    --commit) DO_COMMIT=1; shift ;;
    --update-and-push|--push) DO_COMMIT=1; DO_PUSH=1; shift ;;
    --allow-main) ALLOW_MAIN=1; shift ;;
    --all)
      [[ -f "$TARGETS_FILE" ]] || { echo "Geen $TARGETS_FILE" >&2; exit 1; }
      while IFS= read -r line; do
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        TARGETS+=("$line")
      done < "$TARGETS_FILE"
      shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) TARGETS+=("$1"); shift ;;
  esac
done

(( ${#TARGETS[@]} )) || { echo "Geen repos opgegeven." >&2; exit 1; }

push_with_retry() {
  local repo="$1" branch="$2"
  local delay=2
  for attempt in 1 2 3 4 5; do
    if git -C "$repo" push -u origin "$branch"; then
      return 0
    fi
    if (( attempt < 5 )); then
      echo "       push faalde, retry over ${delay}s..."
      sleep "$delay"
      delay=$(( delay * 2 ))
    fi
  done
  return 1
}

for repo in "${TARGETS[@]}"; do
  repo="${repo/#~/$HOME}"
  if [[ ! -d "$repo/.git" ]]; then
    echo "  skip $repo (geen git repo)"
    continue
  fi

  dst="$repo/.claude/skills/token-zuinig/SKILL.md"
  mkdir -p "$(dirname "$dst")"

  changed=0
  if [[ ! -f "$dst" ]] || ! cmp -s "$SRC" "$dst"; then
    cp "$SRC" "$dst"
    changed=1
    echo "  copy $repo"
  else
    echo "  ok   $repo (al up-to-date)"
  fi

  (( DO_COMMIT )) || continue
  (( changed )) || continue

  git -C "$repo" add .claude/skills/token-zuinig/SKILL.md
  if git -C "$repo" diff --cached --quiet; then
    echo "       niets te committen"
    continue
  fi

  git -C "$repo" commit -m "Update token-zuinig skill" >/dev/null
  echo "       committed"

  (( DO_PUSH )) || continue

  branch=$(git -C "$repo" symbolic-ref --short HEAD 2>/dev/null || echo "")
  if [[ -z "$branch" ]]; then
    echo "       skip push (detached HEAD)"
    continue
  fi
  if [[ "$branch" =~ ^(main|master)$ ]] && (( ! ALLOW_MAIN )); then
    echo "       skip push (op $branch — gebruik --allow-main of switch eerst naar feature branch)"
    continue
  fi

  if push_with_retry "$repo" "$branch"; then
    echo "       pushed → origin/$branch"
  else
    echo "       PUSH FAILED na 5 pogingen" >&2
  fi
done

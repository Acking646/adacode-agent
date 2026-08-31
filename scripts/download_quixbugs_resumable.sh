#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/jkoppel/QuixBugs.git}"
OUTPUT_DIR="${OUTPUT_DIR:-./data/open/QuixBugs}"
GIT_PROXY="${GIT_PROXY:-${https_proxy:-${HTTPS_PROXY:-}}}"
RETRIES="${RETRIES:-20}"
SLEEP_SECONDS="${SLEEP_SECONDS:-20}"

echo "Repository: $REPO_URL"
echo "Output:     $OUTPUT_DIR"
echo "GIT_PROXY:  ${GIT_PROXY:-<none>}"

git_args=(-c http.version=HTTP/1.1 -c http.lowSpeedLimit=0)
if [[ -n "$GIT_PROXY" ]]; then
  git_args+=(-c "http.proxy=$GIT_PROXY" -c "https.proxy=$GIT_PROXY")
fi

for attempt in $(seq 1 "$RETRIES"); do
  echo "Clone/update attempt $attempt/$RETRIES"
  if [[ -d "$OUTPUT_DIR/.git" ]]; then
    if git "${git_args[@]}" -C "$OUTPUT_DIR" fetch --all --prune; then
      git "${git_args[@]}" -C "$OUTPUT_DIR" checkout master || git "${git_args[@]}" -C "$OUTPUT_DIR" checkout main
      git "${git_args[@]}" -C "$OUTPUT_DIR" pull --ff-only || true
      echo "Done."
      exit 0
    fi
  else
    rm -rf "$OUTPUT_DIR"
    mkdir -p "$(dirname "$OUTPUT_DIR")"
    if git "${git_args[@]}" clone --depth 1 "$REPO_URL" "$OUTPUT_DIR"; then
      echo "Done."
      exit 0
    fi
  fi
  echo "Download failed; sleeping ${SLEEP_SECONDS}s before retry..."
  sleep "$SLEEP_SECONDS"
done

echo "Failed to download QuixBugs after $RETRIES attempts." >&2
exit 1

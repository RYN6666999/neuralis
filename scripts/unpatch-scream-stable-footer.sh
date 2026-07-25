#!/usr/bin/env bash
set -euo pipefail

dist_dir="/opt/homebrew/lib/node_modules/scream-code/dist"
target="$(ls -1 "$dist_dir"/app-*.mjs 2>/dev/null | head -1 || true)"

if [[ -z "$target" ]]; then
  echo "❌ 找不到 app-*.mjs"
  exit 1
fi

backup="${target}.stable-footer-bak"
if [[ ! -f "$backup" ]]; then
  echo "⚠️ 找不到備份：$backup"
  exit 1
fi

cp "$backup" "$target"
node --check "$target" >/dev/null
echo "✅ 已還原 stable footer 補丁：$(basename "$target")"

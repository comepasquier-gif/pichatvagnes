#!/bin/bash
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$(osascript -e 'POSIX path of (choose folder with prompt "Choisis le dossier pichatvagnes surveillé par GitHub Desktop")')"
TARGET="${TARGET%/}"

if [ ! -d "$TARGET/backend" ] || [ ! -d "$TARGET/frontend" ]; then
  osascript -e 'display alert "Mauvais dossier" message "Choisis la racine du dépôt PiChat contenant backend et frontend." as critical'
  exit 1
fi

FILES=(
"backend/config.py"
"backend/services/integration_hub_service.py"
"backend/services/ai_service.py"
"backend/services/direct_message_service.py"
"frontend/index.html"
"frontend/admin.html"
"frontend/pibrawl.html"
"frontend/service-worker.js"
"frontend/css/fix362.css"
"frontend/css/pibrawl.css"
"frontend/js/fix362.js"
"frontend/js/pibrawl.js"
"frontend/js/admin_integrations.js"
"frontend/js/admin35.bundle.js"
"VERSION.txt"
"CHANGELOG_3.6.md"
)

for rel in "${FILES[@]}"; do
  mkdir -p "$TARGET/$(dirname "$rel")"
  cp -f "$BASE/PATCH_FILES/$rel" "$TARGET/$rel"
done

osascript -e 'display dialog "PiChat 3.6.2 appliqué. Dans GitHub Desktop : Commit to main puis Push origin." buttons {"OK"} default button "OK" with icon note'
open -a "GitHub Desktop" "$TARGET" 2>/dev/null || true

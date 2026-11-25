#!/bin/sh
# Copia template/ (de la etiqueta stable) al repo plantilla pegongorasep/garmin-dashboard-template.
# Los repos de amigos ya creados no cambian: solo afecta a quien cree uno nuevo desde la plantilla.
# Uso: scripts/sync_template.sh   (después de mover stable)
set -e
REPO=pegongorasep/garmin-dashboard-template
MOTOR=$(cd "$(dirname "$0")/.." && pwd)
SHA=$(git -C "$MOTOR" rev-parse --short stable)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
gh repo clone "$REPO" "$TMP/plantilla" -- --quiet
git -C "$MOTOR" archive stable template | tar -x -C "$TMP"
rsync -a --delete --exclude .git "$TMP/template/" "$TMP/plantilla/"
cd "$TMP/plantilla"
if [ -z "$(git status --porcelain)" ]; then
  echo "La plantilla ya está al día."
  exit 0
fi
git add -A
git commit -q -m "Plantilla al día (motor $SHA)"
git push -q
echo "Plantilla actualizada: https://github.com/$REPO"

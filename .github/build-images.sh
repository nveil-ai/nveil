#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 NVEIL SAS
# SPDX-FileContributor: Pierre Jacquet
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Build (and optionally push) the NVEIL Community Edition images to GHCR.
#
# These are the *self-contained* images: the Dockerfiles COPY the backend, the
# built frontend and the example data into the image, so a user can run the
# stack from the images alone — no source checkout, unlike the dev compose which
# mounts ./nveil/backend over them for live reload.
#
# Lives in .github/ so a GitHub Action can wrap it later (build + push on tag).
#
# Usage (run from anywhere — the script cd's to the repo root itself):
#   .github/build-images.sh                  # build all images locally (no push)
#   PUSH=1 .github/build-images.sh           # build + push to GHCR (run `docker login ghcr.io` first)
#   SERVICES="server ai" .github/build-images.sh    # build a subset
#   REGISTRY=ghcr.io/you .github/build-images.sh    # override the registry/namespace
#
# Env knobs (all optional):
#   REGISTRY     image namespace            (default: ghcr.io/nveil-ai)
#   PLATFORM     target platform            (default: linux/amd64)
#   PUSH         1 to docker push           (default: 0)
#   VITE_GTM_ID  Google Tag Manager id      (default: empty → community images ship tracking-free)
#   SERVICES     space-separated subset     (default: all)

set -euo pipefail
cd "$(dirname "$0")/.."   # repo root — the build context for every image

REGISTRY="${REGISTRY:-ghcr.io/nveil-ai}"
PLATFORM="${PLATFORM:-linux/amd64}"
PUSH="${PUSH:-0}"
VITE_GTM_ID="${VITE_GTM_ID:-}"
VERSION="$(tr -d '[:space:]' < VERSION)"

# service | dockerfile | published image name
ALL_SERVICES=(
  "server:docker/server/dockerfile:nveil-server"
  "ai:docker/ai/dockerfile:nveil-ai"
  "file:docker/file/dockerfile:nveil-file"
  "viz:docker/visualization/dockerfile:nveil-viz"
  "setup:docker/setup/Dockerfile:nveil-setup"
)
WANT="${SERVICES:-server ai file viz setup}"

echo "NVEIL Community images  |  version=$VERSION  platform=$PLATFORM  registry=$REGISTRY  push=$PUSH"
[ -n "$VITE_GTM_ID" ] && echo "  (server built WITH VITE_GTM_ID=$VITE_GTM_ID — analytics enabled)"

for entry in "${ALL_SERVICES[@]}"; do
  IFS=: read -r svc dockerfile image <<< "$entry"
  case " $WANT " in *" $svc "*) ;; *) continue ;; esac

  ref="$REGISTRY/$image"
  echo ""
  echo "── building $svc → $ref:{$VERSION,latest}"

  build_args=()
  [ "$svc" = "server" ] && build_args+=(--build-arg "VITE_GTM_ID=$VITE_GTM_ID")

  docker build \
    --platform "$PLATFORM" \
    -f "$dockerfile" \
    -t "$ref:$VERSION" \
    -t "$ref:latest" \
    "${build_args[@]}" \
    .

  if [ "$PUSH" = "1" ]; then
    docker push "$ref:$VERSION"
    docker push "$ref:latest"
    echo "   pushed $ref:$VERSION and :latest"
  fi
done

echo ""
if [ "$PUSH" = "1" ]; then
  echo "Done — images pushed to $REGISTRY."
else
  echo "Done (local only). To publish: 'docker login ghcr.io' then  PUSH=1 .github/build-images.sh"
fi

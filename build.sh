#!/bin/bash

# Build and Push to Docker Hub Script
# Usage: ./build-and-push.sh [version_tag]

set -e

# Configuration
DOCKER_USERNAME="infyrus"  # Replace with your Docker Hub username
IMAGE_NAME="rbl-sourcing-portal"
VERSION=${1:-latest}

echo "🚀 Building and pushing RBL Sourcing Portal..."
echo "Image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"

# Build the image
echo "📦 Building Docker image..."
docker build -t ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} .

# Tag as latest if not already
if [ "$VERSION" != "latest" ]; then
    docker tag ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
fi

# Login to Docker Hub (you'll be prompted for credentials)
echo "🔑 Logging in to Docker Hub..."
docker login

# Push the image
echo "⬆️ Pushing to Docker Hub..."
docker push ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}

if [ "$VERSION" != "latest" ]; then
    docker push ${DOCKER_USERNAME}/${IMAGE_NAME}:latest
fi

echo "✅ Successfully pushed ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} to Docker Hub!"
echo ""
echo "To deploy, update your compose.yml with:"
echo "  image: ${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}"
echo ""
echo "Then run: docker-compose up -d"

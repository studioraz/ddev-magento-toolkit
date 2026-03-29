#!/bin/bash
#ddev-generated

# Define the repository to check
REPO_URL="https://github.com/studioraz/ddev-magento-toolkit"
ADDON_NAME="ddev-magento-toolkit"

echo "Checking for updates for $ADDON_NAME..."

# 1. Get the latest tag from the remote repository
LATEST_VERSION=$(git ls-remote --tags --refs --sort='-v:refname' "$REPO_URL" | head -n 1 | sed 's|.*/||')

# 2. Get the currently installed version using jq to parse the DDEV JSON output
# This looks into the "raw" array for the object matching our addon name
INSTALLED_VERSION=$(ddev addon list --installed -j | jq -r ".raw[] | select(.Name==\"$ADDON_NAME\") | .Version")

# Check if we actually found an installed version
if [ -z "$INSTALLED_VERSION" ]; then
    echo "Error: Add-on '$ADDON_NAME' does not appear to be installed in this project."
    exit 1
fi

if [ "$LATEST_VERSION" != "$INSTALLED_VERSION" ]; then
    ddev addon get studioraz/ddev-magento-toolkit
else
    echo "✅ You are running the latest version: $INSTALLED_VERSION."
fi

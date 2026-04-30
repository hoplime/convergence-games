#!/usr/bin/env bash
set -euo pipefail

APP_NAME="${1:?Usage: $0 <app-name> <storage-account-name>}"
STORAGE_ACCOUNT="${2:?Usage: $0 <app-name> <storage-account-name>}"
ROLE="Storage Blob Data Contributor"

# Find or create app registration
APP_ID=$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)
if [ -n "$APP_ID" ]; then
    echo "Found existing app registration: $APP_ID"
else
    echo "Creating app registration: $APP_NAME"
    APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
    echo "Created app: $APP_ID"
fi

# Find or create service principal
SP_ID=$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv)
if [ -n "$SP_ID" ]; then
    echo "Service principal already exists: $SP_ID"
else
    echo "Creating service principal..."
    SP_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
    echo "Created service principal: $SP_ID"
fi

# Add new secret (doesn't touch existing ones)
echo "Adding client secret (valid 2 years)..."
SECRET=$(az ad app credential reset --id "$APP_ID" --append --years 2 --query password -o tsv)

TENANT_ID=$(az account show --query tenantId -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
SCOPE="/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$(
    az storage account show --name "$STORAGE_ACCOUNT" --query resourceGroup -o tsv
)/providers/Microsoft.Storage/storageAccounts/$STORAGE_ACCOUNT"

# Assign role if not already assigned
EXISTING=$(az role assignment list --assignee "$APP_ID" --role "$ROLE" --scope "$SCOPE" --query "[0].id" -o tsv)
if [ -n "$EXISTING" ]; then
    echo "Role '$ROLE' already assigned."
else
    echo "Assigning '$ROLE' on $STORAGE_ACCOUNT..."
    az role assignment create \
        --assignee "$APP_ID" \
        --role "$ROLE" \
        --scope "$SCOPE" \
        --output none
fi

cat <<EOF

Done. Add these to your .env:

AZURE_CLIENT_ID=$APP_ID
AZURE_TENANT_ID=$TENANT_ID
AZURE_CLIENT_SECRET=$SECRET
EOF

#!/bin/bash
# Pre-commit hook to prevent committing .env files

# Check if .env is being committed
if git diff --cached --name-only | grep -q "^\.env$"; then
    echo "❌ ERROR: Attempting to commit .env file!"
    echo ""
    echo "The .env file contains sensitive information and should not be committed."
    echo "If you need to commit environment variable examples, use .env.example instead."
    echo ""
    echo "To fix this:"
    echo "  1. Unstage the .env file: git reset HEAD .env"
    echo "  2. Ensure .env is in .gitignore"
    echo ""
    exit 1
fi

# Check for any .env files in the staging area
if git diff --cached --name-only | grep -q "\.env"; then
    echo "⚠️  WARNING: Found .env files in staging area!"
    echo "Please ensure these are example files (.env.example) and not actual credential files."
    echo ""
fi

exit 0

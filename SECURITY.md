# Security Policy

## Supported Versions

We actively support the latest version of this project. Please update to the latest version to receive security updates.

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue. Instead, please report it privately by:

1. Opening a private security advisory on GitHub
2. Or contacting the maintainers directly

We will respond to security reports as quickly as possible.

## Security Best Practices

### API Keys and Credentials

**NEVER commit sensitive information to the repository:**

- ✅ **DO**: Use environment variables (`.env` file)
- ✅ **DO**: Keep `.env` in `.gitignore`
- ✅ **DO**: Use `.env.example` as a template
- ❌ **DON'T**: Commit `.env` files
- ❌ **DON'T**: Hardcode API keys in source code
- ❌ **DON'T**: Share API keys in issues or pull requests

### If You Accidentally Commit Credentials

If you accidentally commit sensitive information:

1. **Immediately rotate/revoke the exposed credentials**
2. Remove the file from git history:
   ```bash
   git filter-branch --force --index-filter \
     "git rm --cached --ignore-unmatch .env" \
     --prune-empty --tag-name-filter cat -- --all
   ```
3. Force push (if already pushed):
   ```bash
   git push origin --force --all
   ```
4. Notify the maintainers if it's a shared repository

### Environment Variables

Always use environment variables for:
- API keys
- Authentication tokens
- Database credentials
- Any sensitive configuration

### Code Review

Before merging pull requests, ensure:
- No `.env` files are included
- No hardcoded credentials
- Environment variables are properly documented in `.env.example`

## Dependencies

We regularly update dependencies to patch security vulnerabilities. Always use the latest versions of dependencies specified in `requirements.txt`.

## Data Privacy

This tool processes publicly available app reviews from Google Play Store. We do not:
- Store personal information
- Share data with third parties
- Track user behavior

All analysis is performed locally or through authenticated API calls.

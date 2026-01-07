# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Email:** security@henrywallace.io
2. **Include:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

**Please do not** open a public GitHub issue for security vulnerabilities.

We will acknowledge receipt within 48 hours and provide an update on the status of the vulnerability within 7 days.

## Security Best Practices

### For Package Users

1. **Always use environment variables** for API keys
   - Never hardcode secrets in your code
   - Use `.env` files (not committed to git)
   - Rotate keys regularly

2. **Enable secret detection**
   - Use the provided pre-commit hook
   - Review `.secretsignore.example` for configuration
   - Run `node scripts/detect-secrets.mjs --scan-history` periodically

3. **Validate inputs**
   - Validate file paths before passing to functions
   - Sanitize user-provided prompts
   - Set reasonable size limits on inputs

4. **Monitor API usage**
   - Set up rate limiting if using the API
   - Monitor for unusual patterns
   - Review error logs regularly

5. **Keep dependencies updated**
   - Regularly update `@playwright/test` peer dependency
   - Run `npm audit` regularly
   - Review security advisories

### For Contributors

1. **Follow secure coding practices**
   - Never commit secrets
   - Use the pre-commit hook
   - Review code for security issues

2. **Test security features**
   - Add security-focused tests
   - Test input validation
   - Test error handling

3. **Document security considerations**
   - Document any security assumptions
   - Note any known limitations
   - Update this file for new vulnerabilities

## Known Security Considerations

### API Endpoint (`/api/validate`)

- **Authentication** - Optional API key authentication via `API_KEY` or `VLLM_API_KEY` environment variable
  - Set `REQUIRE_AUTH=true` to enforce authentication
  - API key can be provided via `X-API-Key` header or `Authorization: Bearer <key>` header
- **Rate Limiting** - Built-in rate limiting (10 requests/minute by default, configurable via `RATE_LIMIT_MAX_REQUESTS`)
  - Rate limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
  - Returns 429 status when limit exceeded
  - Uses in-memory store (use Redis for production multi-instance deployments)
- **Error messages** - Sanitized to prevent information leakage

### File Operations

- **Path validation** - Always validate file paths before use
- **Temporary files** - Cleaned up automatically, but ensure proper error handling

### Environment Variables

- **No validation** - Validate required environment variables at startup
- **No encryption** - Store sensitive values securely

## Security Features

- ✅ Pre-commit secret detection (enhanced with red team recommendations)
- ✅ Git history scanning option
- ✅ Zero runtime dependencies
- ✅ Input validation
- ✅ Error handling with sanitization
- ✅ Rate limiting (configurable, in-memory or Redis)
- ✅ Authentication (optional API key)
- ✅ Path traversal protection
- ✅ Size limits on all inputs

## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for security-related updates.


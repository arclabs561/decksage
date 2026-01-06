# Security Policy

## Supported Versions

We currently support security updates for the latest version of DeckSage.

| Version | Supported          |
| ------- | ------------------ |
| Latest  | :white_check_mark: |
| < Latest| :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not** open a public issue.

Instead, please report it via one of the following methods:

1. **GitHub Security Advisory**: Use GitHub's private vulnerability reporting feature
2. **Email**: [Add security contact email if available]
3. **Private Issue**: Create a private issue (if you have access)

### What to Include

When reporting a vulnerability, please include:

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

### Response Time

We aim to acknowledge security reports within 48 hours and provide an initial assessment within 7 days.

## Security Best Practices

When using DeckSage:

- Keep dependencies up to date: `uv sync`
- Review API authentication if deploying publicly
- Don't commit API keys or secrets
- Use environment variables for sensitive configuration

## Known Security Considerations

- **API Keys**: Store API keys (e.g., `OPENROUTER_API_KEY`) in environment variables, not in code
- **Data Files**: Large data files are stored locally/S3, not in git
- **Dependencies**: Regular dependency updates via Dependabot

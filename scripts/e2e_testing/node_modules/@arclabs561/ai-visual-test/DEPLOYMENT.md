# Deployment Guide

## Vercel Deployment

### Quick Deploy

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd /path/to/ai-visual-test
vercel
```

### Environment Variables

Set these in Vercel dashboard:

- `GEMINI_API_KEY` (or `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`)
- `VLM_PROVIDER` (optional)
- `API_KEY` or `VLLM_API_KEY` (optional, for API authentication)
- `REQUIRE_AUTH` (optional, set to `true` to enforce authentication)
- `RATE_LIMIT_MAX_REQUESTS` (optional, default: 10 requests per minute)

### API Endpoints

After deployment, you'll have:

- `https://your-site.vercel.app/api/validate` - Validation endpoint
- `https://your-site.vercel.app/api/health` - Health check
- `https://your-site.vercel.app/` - Web interface

### Usage

```javascript
// Validate screenshot (without authentication)
const response = await fetch('https://your-site.vercel.app/api/validate', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    image: base64Image,
    prompt: 'Evaluate this screenshot...',
    context: { testType: 'payment-screen' }
  })
});

const result = await response.json();

// With authentication (if API_KEY is set)
const responseAuth = await fetch('https://your-site.vercel.app/api/validate', {
  method: 'POST',
  headers: { 
    'Content-Type': 'application/json',
    'X-API-Key': 'your-api-key' // or 'Authorization': 'Bearer your-api-key'
  },
  body: JSON.stringify({
    image: base64Image,
    prompt: 'Evaluate this screenshot...',
    context: { testType: 'payment-screen' }
  })
});

// Check rate limit headers
const remaining = response.headers.get('X-RateLimit-Remaining');
const resetAt = response.headers.get('X-RateLimit-Reset');
```

## Local Development

```bash
# Install dependencies
npm install

# Run tests
npm test

# Use as library
import { validateScreenshot } from '@ai-visual-test/core';
```

# Quick Start: decksage.cards Setup

Quick reference for setting up `decksage.cards` with AWS Route 53 and Fly.io.

## Prerequisites

- AWS Account
- Fly.io account (https://fly.io)
- Fly CLI installed: `curl -L https://fly.io/install.sh | sh`

## Quick Setup Steps

### 1. Register Domain (AWS Route 53)

1. Go to https://console.aws.amazon.com/route53/
2. **Domains** → **Registered domains** → **Register domains**
3. Search for `decksage.cards`
4. Add to cart → Checkout → Complete registration
5. Wait for registration (5-15 minutes)

**See detailed guide**: `deploy/aws-route53-setup.md`

### 2. Setup Fly.io App

Run the automated setup script:

```bash
./deploy/flyio-setup.sh
```

Or manually:

```bash
# Login
fly auth login

# Create app
fly apps create decksage

# Allocate IPs (required for TLS)
fly ips allocate-v6 -a decksage
fly ips allocate-v4 -a decksage

# Add domain
fly certs add decksage.cards -a decksage
```

**See detailed guide**: `deploy/flyio-setup.md`

### 3. Configure DNS (Route 53)

1. Get DNS records from Fly.io output (from `fly certs add`)
2. Go to Route 53 → **Hosted zones** → **decksage.cards**
3. Create records:
   - **A record**: IPv4 address from Fly.io
   - **AAAA record**: IPv6 address from Fly.io
4. Wait for DNS propagation (5-60 minutes)

### 4. Verify Certificate

```bash
fly certs check decksage.cards -a decksage
```

Wait until you see: `✓ Certificate issued successfully`

### 5. Set Secrets

```bash
fly secrets set EMBEDDINGS_PATH=/path/to/vectors.kv -a decksage
fly secrets set PAIRS_PATH=/path/to/pairs.csv -a decksage
# Add other secrets as needed
```

### 6. Deploy

```bash
fly deploy -a decksage
```

### 7. Test

```bash
curl https://decksage.cards/live
curl https://decksage.cards/ready
```

## Common Commands

```bash
# Check app status
fly status -a decksage

# View logs
fly logs -a decksage

# Check certificate
fly certs check decksage.cards -a decksage

# List IPs
fly ips list -a decksage

# View secrets
fly secrets list -a decksage
```

## Troubleshooting

### Certificate Not Issuing

1. Ensure IPv6 is allocated: `fly ips allocate-v6 -a decksage`
2. Check DNS: `dig decksage.cards AAAA`
3. Wait for propagation (up to 60 minutes)

### DNS Not Resolving

1. Verify records in Route 53 hosted zone
2. Check name servers match hosted zone
3. Wait for propagation

### App Not Responding

1. Check status: `fly status -a decksage`
2. View logs: `fly logs -a decksage`
3. Verify secrets: `fly secrets list -a decksage`

## Full Documentation

- **AWS Route 53 Setup**: `deploy/aws-route53-setup.md`
- **Fly.io Setup**: `deploy/flyio-setup.md`
- **Automated Script**: `deploy/flyio-setup.sh`

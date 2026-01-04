# AWS Route 53 Domain Registration Guide

This guide walks through registering `decksage.cards` with AWS Route 53.

## Prerequisites

1. AWS Account
2. Access to Route 53 service
3. Valid payment method on file

## Step 1: Register the Domain

### 1.1 Access Route 53 Console

1. Sign in to AWS Console: https://console.aws.amazon.com/route53/
2. Navigate to **Route 53** → **Domains** → **Registered domains**

### 1.2 Search for Domain

1. Click **Register domains**
2. In the **Search for domain** section, enter: `decksage.cards`
3. Click **Search**

### 1.3 Add Domain to Cart

1. If `decksage.cards` is available, click **Add to cart**
2. You can register up to 5 domains at once
3. Click **Proceed to checkout**

### 1.4 Configure Registration

1. **Registration period**: Choose 1 year (recommended) or longer
2. **Auto-renewal**: Enable automatic renewal to avoid expiration
3. Click **Next**

### 1.5 Enter Contact Information

Fill in contact information for:
- **Registrant contact**: Domain owner (required)
- **Administrative contact**: Domain administrator
- **Technical contact**: Technical support
- **Billing contact**: Payment contact

**Important Notes:**
- Use the same information for all contacts (default)
- Use your real name (matching official ID) for registrant
- Some TLDs require verification of contact information
- Privacy protection is available for most TLDs

### 1.6 Privacy Protection

Choose whether to enable privacy protection:
- **Enabled**: Hides contact info from WHOIS queries (recommended)
- **Disabled**: Contact info visible in WHOIS

### 1.7 Review and Submit

1. Review all information
2. Read and accept terms of service
3. Check the confirmation box
4. Click **Submit**

### 1.8 Verify Email (if required)

1. Check your email for verification message
2. Click the verification link
3. Return to Route 53 console → **Domains** → **Requests**
4. Verify status shows "email-address is verified"

## Step 2: Wait for Registration

Domain registration typically completes within 5-15 minutes. You can check status at:
- **Route 53** → **Domains** → **Registered domains**
- **Route 53** → **Domains** → **Requests**

## Step 3: Access Hosted Zone

Route 53 automatically creates a hosted zone for your domain:

1. Go to **Route 53** → **Hosted zones**
2. Find `decksage.cards`
3. Note the 4 name servers (e.g., `ns-123.awsdns-12.com`)

The name servers are automatically configured for your domain registration.

## Step 4: Configure DNS Records

After setting up Fly.io (see `deploy/flyio-setup.md`), you'll need to add DNS records:

### 4.1 Get DNS Records from Fly.io

Run:
```bash
fly certs add decksage.cards -a decksage
```

This will output the DNS records you need to add.

### 4.2 Add A and AAAA Records

1. Go to **Route 53** → **Hosted zones** → **decksage.cards**
2. Click **Create record**
3. Configure:
   - **Record name**: Leave blank (for apex domain) or enter subdomain
   - **Record type**: A (for IPv4) or AAAA (for IPv6)
   - **Value**: IP address from Fly.io
   - **TTL**: 300 (or use default)
4. Click **Create records**

Repeat for both A and AAAA records.

### 4.3 Add CNAME Record (for subdomains like www)

1. Click **Create record**
2. Configure:
   - **Record name**: `www` (or your subdomain)
   - **Record type**: CNAME
   - **Value**: `decksage.fly.dev` (from Fly.io)
   - **TTL**: 300
3. Click **Create records**

## Step 5: Verify DNS Configuration

### 5.1 Check DNS Propagation

Use command line:
```bash
dig decksage.cards A
dig decksage.cards AAAA
```

Or use online tools:
- https://dnschecker.org
- https://www.whatsmydns.net

### 5.2 Verify Name Servers

Ensure name servers match Route 53 hosted zone:
```bash
dig NS decksage.cards
```

## Pricing

- Domain registration: ~$20-30/year for `.cards` TLD
- Hosted zone: $0.50/month (first 25 zones)
- DNS queries: $0.40 per million queries

See: https://aws.amazon.com/route53/pricing/

## Troubleshooting

### Domain Registration Fails

- Check payment method is valid
- Verify contact information is correct
- Check email for verification requirements
- Contact AWS Support if needed

### DNS Not Resolving

- Verify records are created in hosted zone
- Check name servers match hosted zone
- Wait for DNS propagation (can take up to 48 hours)
- Verify TTL settings

### Name Servers Don't Match

If you see different name servers:
1. Go to **Registered domains** → **decksage.cards**
2. Click **Add or edit name servers**
3. Update to match hosted zone name servers

## Additional Resources

- [Route 53 Domain Registration Docs](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/domain-register.html)
- [Route 53 Pricing](https://aws.amazon.com/route53/pricing/)
- [Route 53 Hosted Zones](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/hosted-zones-working-with.html)

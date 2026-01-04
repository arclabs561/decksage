# Fly.io Setup Guide for decksage.cards

This guide walks through setting up `decksage.cards` domain with AWS Route 53 and deploying to Fly.io.

## Prerequisites

1. AWS Account with Route 53 access
2. Fly.io account (sign up at https://fly.io)
3. Fly CLI installed (`curl -L https://fly.io/install.sh | sh`)

## Step 1: Register decksage.cards with AWS Route 53

### 1.1 Register the Domain

1. Sign in to AWS Console: https://console.aws.amazon.com/route53/
2. Navigate to **Route 53** → **Domains** → **Registered domains**
3. Click **Register domains**
4. Search for `decksage.cards`
5. If available, add it to cart and proceed to checkout
6. Choose registration period (1 year recommended)
7. Enable auto-renewal
8. Enter contact information (registrant, admin, tech, billing)
9. Review and submit

### 1.2 Verify Domain Registration

1. Check email for verification (if required by TLD registry)
2. Verify email address if prompted
3. Wait for registration to complete (usually 5-15 minutes)

### 1.3 Note the Hosted Zone

Route 53 automatically creates a hosted zone for your domain. You'll need the name servers later.

1. Go to **Route 53** → **Hosted zones**
2. Find `decksage.cards`
3. Note the 4 name servers (e.g., `ns-123.awsdns-12.com`)

## Step 2: Create Fly.io App

### 2.1 Login to Fly.io

```bash
fly auth login
```

### 2.2 Create the App

```bash
fly apps create decksage
```

### 2.3 Allocate IPv6 Address (Required for TLS)

```bash
fly ips allocate-v6 -a decksage
```

This is required for Fly.io to issue TLS certificates.

### 2.4 Allocate IPv4 Address (Optional but Recommended)

```bash
fly ips allocate-v4 -a decksage
```

## Step 3: Add Custom Domain to Fly.io

### 3.1 Add the Domain

```bash
fly certs add decksage.cards -a decksage
```

This command will output DNS configuration instructions. You'll see:
- A and AAAA records to add
- Or CNAME record option
- DNS-01 challenge record (if needed)

### 3.2 Check Certificate Status

```bash
fly certs check decksage.cards -a decksage
```

## Step 4: Configure DNS in Route 53

### 4.1 Get DNS Records from Fly.io

After running `fly certs add`, you'll see output like:

```
A Record: 123.45.67.89
AAAA Record: 2001:db8::1
```

Or for CNAME:
```
CNAME: decksage.cards -> decksage.fly.dev
```

### 4.2 Add DNS Records in Route 53

1. Go to **Route 53** → **Hosted zones** → **decksage.cards**
2. Click **Create record**

**Option A: A and AAAA Records (Recommended for apex domain)**

- **Record name**: Leave blank (for apex) or enter subdomain
- **Record type**: A
- **Value**: IPv4 address from Fly.io
- **TTL**: 300 (or use default)
- Click **Create records**

Repeat for AAAA record with IPv6 address.

**Option B: CNAME Record (For subdomains like www.decksage.cards)**

- **Record name**: `www` (or your subdomain)
- **Record type**: CNAME
- **Value**: `decksage.fly.dev` (from Fly.io output)
- **TTL**: 300
- Click **Create records**

### 4.3 Wait for DNS Propagation

DNS changes can take 5-60 minutes to propagate. Check with:

```bash
dig decksage.cards A
dig decksage.cards AAAA
```

Or use online tools like https://dnschecker.org

## Step 5: Verify Certificate

### 5.1 Check Certificate Status

```bash
fly certs check decksage.cards -a decksage
```

Wait until you see:
```
✓ Certificate issued successfully
```

### 5.2 View Setup Instructions Again

If needed:
```bash
fly certs setup decksage.cards -a decksage
```

## Step 6: Deploy the Application

### 6.1 Set Environment Variables

```bash
fly secrets set EMBEDDINGS_PATH=/path/to/vectors.kv -a decksage
fly secrets set PAIRS_PATH=/path/to/pairs.csv -a decksage
# Add other secrets as needed
```

### 6.2 Deploy

```bash
fly deploy -a decksage
```

### 6.3 Verify Deployment

```bash
fly status -a decksage
fly logs -a decksage
```

## Step 7: Test the Domain

Once DNS has propagated and certificate is issued:

```bash
curl https://decksage.cards/live
curl https://decksage.cards/ready
```

## Troubleshooting

### Certificate Not Issuing

1. Ensure IPv6 address is allocated: `fly ips allocate-v6 -a decksage`
2. Check DNS records are correct: `dig decksage.cards AAAA`
3. Wait for DNS propagation (can take up to 60 minutes)
4. Check certificate status: `fly certs check decksage.cards -a decksage`

### DNS Not Resolving

1. Verify records in Route 53 hosted zone
2. Check name servers match Route 53 hosted zone
3. Wait for propagation
4. Use `dig` or DNS checker tools

### App Not Responding

1. Check app status: `fly status -a decksage`
2. View logs: `fly logs -a decksage`
3. Check environment variables: `fly secrets list -a decksage`
4. Verify app is running: `fly machine list -a decksage`

## Additional Resources

- [Fly.io Custom Domains Docs](https://fly.io/docs/networking/custom-domain/)
- [AWS Route 53 Domain Registration](https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/domain-register.html)
- [Fly.io CLI Reference](https://fly.io/docs/flyctl/)















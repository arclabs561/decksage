# DNSSEC Status for decksage.cards

## ✅ DNSSEC is Enabled and Active

### Certificate Status
- **Status**: Ready ✓
- **Issued**: RSA + ECDSA certificates
- **Expires**: 2 months from now
- **Auto-renewal**: Enabled

### DNS Resolution
- **A Record**: `188.93.147.85` ✓
- **AAAA Record**: `2a09:8280:1::ae:4a43:0` ✓
- **Name Servers**: AWS Route 53 (ns-1237, ns-1696, ns-409, ns-605)

### DNSSEC Configuration

#### DNSKEY Records (Signing Keys)
- **ZSK (Zone Signing Key)**: Present (256 3 13)
- **KSK (Key Signing Key)**: Present (257 3 13)
- **Algorithm**: ECDSA P-256 (algorithm 13)

#### RRSIG Records (Signatures)
All DNS records are signed:
- ✓ A record signed
- ✓ AAAA record signed  
- ✓ DNSKEY records signed

#### DNSSEC Validation
- DNSSEC signing is **active** and working correctly
- All records have valid RRSIG signatures
- DNSKEY records are properly configured

### Verification Commands

```bash
# Check certificate
fly certs check decksage.cards -a decksage

# Verify DNS resolution
dig +short decksage.cards A
dig +short decksage.cards AAAA

# Check DNSSEC
dig +dnssec decksage.cards
dig +dnssec DNSKEY decksage.cards
```

### Next Steps

The domain and DNS are fully configured. To deploy the application:

```bash
# Set environment variables (if needed)
fly secrets set EMBEDDINGS_PATH=/path/to/vectors.kv -a decksage
fly secrets set PAIRS_PATH=/path/to/pairs.csv -a decksage

# Deploy
fly deploy -a decksage

# Test
curl https://decksage.cards/live
curl https://decksage.cards/ready
```














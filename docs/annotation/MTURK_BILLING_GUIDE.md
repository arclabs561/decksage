# MTurk Billing and Payment Guide

## Current Status

✅ **Account Linked**: AWS Account 512827140002 is linked to MTurk Requester Account
✅ **API Access**: Working correctly (can query balance, create HITs)
✅ **AWS Billing**: Configured and enabled - charges go to AWS account automatically
✅ **Ready to Use**: Can submit HITs immediately (no prepaid balance needed)

## Billing Method

### AWS Billing (Active) ✅

**Your account is configured to pay using AWS billing**:
- Charges automatically go to your AWS account
- No prepaid balance needed
- Billed monthly on your AWS invoice
- Can submit HITs immediately

**Status**: Confirmed active in account settings

### Prepaid Balance (No Longer Available)

**Important**: As of August 30, 2023, MTurk no longer supports payment of Prepaid HITs via credit card.

All accounts must use AWS billing. Your account is already configured for this.

### Option 3: Developer Sandbox (For Testing)

**Free Testing Environment**:
- Register at: MTurk Developer Sandbox
- Always has $10,000 virtual balance
- Full API parity with production
- No real charges

**Use for**:
- Testing HIT creation
- Validating task formats
- API integration testing
- Quality assurance

## Current Account Details

- **AWS Account**: 512827140002
- **Account Holder**: Henry Wallace
- **Contact**: admin@henrywallace.io
- **Status**: Linked and active
- **Balance**: $0.02 (production)

## Recommended Approach

1. **For Testing**: Use Developer Sandbox (free, $10k virtual balance)
2. **For Production**: 
   - ✅ AWS billing is already enabled
   - ✅ Ready to submit HITs immediately
   - Charges will appear on AWS bill automatically

## Testing Without Balance

You can test the complete integration using:
- **Sandbox**: Full testing with virtual funds
- **Custom Service**: Internal/expert annotation (no cost)
- **Scale AI**: Once API access is enabled

## Next Steps

1. ✅ Account is linked and API working
2. ✅ AWS billing is enabled and configured
3. ✅ Ready to submit HITs immediately
4. ✅ Code is ready to submit HITs

**You can start using MTurk production environment now** - charges will go to your AWS account automatically.

## References

- [MTurk Developer Guide](https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMechanicalTurkRequester/SetUpMturk.html)
- [MTurk Support](mailto:mturk-support@amazon.com)
- [AWS Billing Console](https://console.aws.amazon.com/billing/)


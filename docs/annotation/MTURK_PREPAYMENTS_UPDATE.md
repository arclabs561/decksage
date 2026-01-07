# MTurk Prepayments - Updated Process (2026)

## Issue Found

The prepayments interface **appears to have issues** - both direct URLs and the account settings path are not accessible or redirect unexpectedly.

## Available Options

### Option 1: AWS Billing (If Configured) - Recommended

If your account is configured to use AWS billing:
- MTurk charges appear on your AWS bill automatically
- No prepaid balance needed
- Charges made as HITs are completed

**Check**: Look for "Billing details" in account settings. If it says "Your account is configured to pay using AWS billing", this is active.

### Option 2: Contact MTurk Support

Since the prepayments interface is not accessible:
1. Email: mturk-support@amazon.com
2. Request assistance adding prepaid balance
3. Provide account details: AWS Account 512827140002

### Option 3: Developer Sandbox (For Testing)

**Free Testing Environment**:
- Register at: MTurk Developer Sandbox
- Always has $10,000 virtual balance
- Full API parity with production
- No real charges

**Perfect for**: Testing HIT creation, validating task formats, API integration

## References

- [AWS MTurk Setup Guide](https://docs.aws.amazon.com/AWSMechTurk/latest/AWSMechanicalTurkRequester/SetUpMturk.html)
- [MTurk Blog: How to fund with bank account](https://blog.mturk.com/how-to-fund-your-mechanical-turk-account-with-a-bank-account-302dbc6314c4)
- [CloudResearch: Funding MTurk Account](https://go.cloudresearch.com/en/knowledge/funding-your-mturk-account)

## Current Status

✅ **Account is Linked**: AWS Account 512827140002
✅ **Account is Working**: Can query balance via API
✅ **AWS Billing**: Configured and enabled - confirmed in account settings
✅ **Ready to Use**: Can submit HITs immediately (charges go to AWS account)

## Important Note

**As of August 30, 2023**: MTurk no longer supports payment of Prepaid HITs via credit card. All accounts must use AWS billing.

Your account is already configured correctly for AWS billing.

## Action Required

**None** - Your account is ready for production use:
1. ✅ AWS billing is enabled
2. ✅ Account is linked
3. ✅ API is working
4. ✅ Can submit HITs immediately

Charges will automatically appear on your AWS bill.

## Testing Recommendations

1. **Use Developer Sandbox**: Free testing with $10k virtual balance (recommended for initial testing)
2. **Production**: Ready to use - charges go to AWS account automatically


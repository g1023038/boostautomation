# Booost Buy -- functional test checklist

Source: Booost Test Plan Vouchers & VAS (LRQA-6883), Beta Readiness Test Plan
(LRQA-7027), Booost Buy architecture doc, via Rovo/Confluence/Jira.
Payment test values live in `ppe_payment_and_vas.json` next to this file.

## Module 1 -- purchase details capture
- Fixed vs. variable denomination (pre-set tile vs. typed Rand value)
- Boundary limits: below min (e.g. < R10 should block) and above max (e.g. > R5,000 should warn)
- Quantity add/increase/decrease
- Input sanitization: non-numeric, decimals, commas, whitespace

## Module 2 -- real-time meter validation (electricity VAS)
- Valid meter number resolves a customer name/address
- Invalid/short meter number shows an instant validation error
- Vendor API timeout is handled gracefully (retry prompt, no crash)

## Module 3 -- basket & cart management
- Multi-item basket across different aggregators
- Remove/adjust quantity, total recalculates live
- Empty cart blocks "Proceed to checkout"
- Cart persists across app background/close/reopen

## Module 4 -- T&Cs and purchase summary
- Payment blocked until T&Cs checkbox is ticked
- Summary shows line items, Rand vs. Boost points breakdown, fees, destination
- Back from summary preserves captured amounts/parameters

## Module 5 -- voucher receipt & fulfillment
- Instant in-app receipt (barcode/QR/wiCode PIN) on success
- Delayed vendor response shows "Processing" rather than failing early
- Voucher is never issued while payment is pending or failed

## Module 6 -- post-purchase, history, reversals
- Voucher Wallet (Booost Buy > Vouchers) shows new voucher with expiry
- Purchase history shows correct date, order number, payment split
- Unredeemed voucher refund restores points + card refund
- Redeemed voucher reversal is strictly blocked

## Payment method matrix (see ppe_payment_and_vas.json for exact test values)
| Method | Expected result |
|---|---|
| Full card | Full card charge, transaction ref generated, voucher issued immediately |
| Full Boost points | 0 ZAR card charge, points deducted live, skips the Peach gateway entirely |
| Split-tender (points + card) | Points burned first, then card; card failure rolls back the points burn |
| Declined card | Graceful error, cart preserved, any reserved points released |
| Rapid double-tap on Pay | Button disables on first press, exactly one order created |

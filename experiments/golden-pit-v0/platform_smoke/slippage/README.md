# Smoke #5 — Slipage Model Comparison

Run all three scripts on the **same backtest parameters**:

- Model: `000300.XSHG` first constituent
- Date: 2021-06-01 ~ 2021-06-03
- Frequency: minute
- Capital: 100,000

Each script uses a **different slippage model**. Collect results, then compare.

| Script | Slippage Model |
|--------|---------------|
| smoke_slippage_none.py | NoSlippage |
| smoke_slippage_fixed.py | FixedSlippage(0.001) |
| smoke_slippage_price_related.py | PriceRelatedSlippage(0.001) |

All three use: same stock, same amount (100 shares), same time (09:31).

Output from each:
```
[SMOKE-5] MODEL=... stock=... ref_price=... fill_price=... gap_abs=... gap_bps=... side=buy order_status=...
```

Collect results into `slippage_results.md`, then compare.

from core import *

year_start = datetime(2024, 1, 1)
year_end = datetime(2024, 12, 31)

fx = FXRates(year_start, year_end)

events = []
events += parse_equity_award_csv(
    "EquityAwardsCenter.csv", "ASDF", fx
)
events += parse_brokerage_csv(
    "Individual_Transactions.csv", "ASDF", fx
)

pmavg_end, qty_end, realized_pl, audit_logs = process_events_with_audit(
    events, 0.0, 0.0
)

for a in audit_logs:
    print(a)

total_gains = sum(
    log.realized_pl_eur
    for log in audit_logs
    if log.realized_pl_eur and log.realized_pl_eur > 0
)

total_losses = sum(
    -log.realized_pl_eur
    for log in audit_logs
    if log.realized_pl_eur and log.realized_pl_eur < 0
)

print("Year summary:")
print("\tEnd of year PMAVG (EUR):", round(pmavg_end, 6))
print("\tEnd of year stock quantity:", qty_end)
print("\tRealized P/L (EUR):", round(realized_pl, 2))

print("E1kv:")
print(f"\tKennzahl 994: {round(total_gains, 2)}")
print(f"\tKennzahl 892: {round(total_losses, 2)}")

import argparse
from datetime import datetime
import sys

from core import *

def parse_args():
    p = argparse.ArgumentParser(
        description="E1kv Schani"
    )

    p.add_argument("--taxyear", type=int, required=True)
    p.add_argument("--symbol", type=str, required=True)

    p.add_argument("--broker-csv", required=True)
    p.add_argument("--equity-csv", required=True)

    p.add_argument("--pmavg-start", type=float, default=0.0)
    p.add_argument("--qty-start", type=float, default=0.0)

    p.add_argument(
        "--audit-format",
        choices=["human", "csv"],
        default="human",
    )

    p.add_argument(
        "--audit-output",
        help="Path to audit CSV (required if audit-format=csv)"
    )

    return p.parse_args()

def format_audit_human(log: AuditLog) -> str:
    lines = [
        f"{log.date.date()} | {log.event_type}",
        f"  Qty: {log.qty}",
        f"  Unit price (USD): {round(log.unit_price_usd, 6)}",
        f"  FX rate: {round(log.fx_rate, 6)}",
        f"  Unit price (EUR): {round(log.unit_price_eur, 6)}",
        f"  Qty before: {log.qty_before}",
        f"  PMAVG before: {round(log.pmavg_before, 6)}",
        f"  Qty after: {log.qty_after}",
        f"  PMAVG after: {round(log.pmavg_after, 6)}",
    ]

    if log.realized_pl_eur is not None:
        lines += [
            f"  Proceeds (EUR): {round(log.proceeds_eur, 2)}",
            f"  Cost basis (EUR): {round(log.cost_basis_eur, 2)}",
            f"  Realized P/L (EUR): {round(log.realized_pl_eur, 2)}",
        ]

    return "\n".join(lines)

def main():
    args = parse_args()

    if args.audit_format == "csv" and not args.audit_output:
        print("ERROR: --audit-output required when --audit-format=csv")
        sys.exit(1)

    year_start = datetime(args.taxyear, 1, 1)
    year_end   = datetime(args.taxyear, 12, 31)

    fx = FXRates(year_start, year_end)

    events = []
    events += parse_equity_award_csv(
        args.equity_csv, args.symbol, fx, args.taxyear
    )
    events += parse_brokerage_csv(
        args.broker_csv, args.symbol, fx, args.taxyear
    )

    pmavg_end, qty_end, realized_pl, audit_logs = process_events_with_audit(
        events,
        pmavg_start=args.pmavg_start,
        qty_start=args.qty_start,
    )

    # ---- AUDIT OUTPUT ----
    if args.audit_format == "human":
        for log in audit_logs:
            print(format_audit_human(log))
    else:
        export_audit_csv(audit_logs, args.audit_output)
        print(f"Audit CSV written to {args.audit_output}")

    # ---- E1KV AGGREGATION ----
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

    print(f"\nYear {args.taxyear} summary:")
    print(f"\tEnd of year PMAVG (EUR): {round(pmavg_end, 6)}")
    print(f"\tEnd of year stock quantity: {qty_end}")
    print(f"\tRealized P/L (EUR): {round(realized_pl, 2)}")

    print("\nE1kv:")
    print(f"\tKennzahl 994: {round(total_gains, 2)}")
    print(f"\tKennzahl 892: {round(total_losses, 2)}")


if __name__ == "__main__":
    main()

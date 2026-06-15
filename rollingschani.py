import argparse
from datetime import datetime
import sys
import csv
import json

from core import *


def parse_args():
    p = argparse.ArgumentParser(description="E1kv Rolling Schani — auto-detect start year and process through today")

    p.add_argument("--symbol", type=str, required=True)
    p.add_argument("--broker-csv", required=True)
    p.add_argument("--equity-csv", required=True)
    p.add_argument("--audit-format", choices=["human", "csv"], default="human")
    p.add_argument("--audit-output",
                   help="Filename prefix for audit CSVs (produces prefix_SYMBOL_YEAR.csv per year)")

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


def save_carry(path: str, taxyear: int, symbol: str, pmavg: Decimal, qty: Decimal):
    data = {
        "taxyear": taxyear,
        "symbol": symbol,
        "pmavg": str(pmavg),
        "qty": str(qty),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def detect_start_year(broker_csv: str, equity_csv: str) -> int:
    """Scan both CSVs and return the earliest year found across all rows."""
    earliest = None

    for path in [broker_csv, equity_csv]:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw = row.get("Date")
                if not raw:
                    continue
                try:
                    year = parse_schwab_date(raw).year
                    if earliest is None or year < earliest:
                        earliest = year
                except ValueError:
                    continue

    if earliest is None:
        raise ValueError("Could not detect a start year from the provided CSV files.")

    return earliest


def run_single_year(
    taxyear: int,
    symbol: str,
    broker_csv: str,
    equity_csv: str,
    pmavg_start: Decimal,
    qty_start: Decimal,
    audit_format: str,
    audit_output: str | None,
):
    year_start = datetime(taxyear, 1, 1)
    year_end = datetime(taxyear, 12, 31)

    fx = FXRates(year_start, year_end)

    events = []
    events += parse_equity_award_csv(equity_csv, symbol, fx, taxyear)
    events += parse_brokerage_csv(broker_csv, symbol, fx, taxyear)

    pmavg_end, qty_end, realized_pl, audit_logs = process_events_with_audit(
        events,
        pmavg_start=pmavg_start,
        qty_start=qty_start,
    )

    if audit_format == "human":
        for log in audit_logs:
            print(format_audit_human(log))
    elif audit_format == "csv" and audit_output:
        export_audit_csv(audit_logs, audit_output)
        print(f"  Audit CSV written to {audit_output}")

    return pmavg_end, qty_end, audit_logs


def print_year_summary(taxyear, pmavg_start, qty_start, pmavg_end, qty_end, audit_logs, carry_out):
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
    net = total_gains - total_losses
    sign = "+" if net >= 0 else ""

    print(f"\n{'='*60}")
    print(f"  Year {taxyear} summary")
    print(f"{'='*60}")
    print(f"  Start of year PMAVG (EUR):   {round(pmavg_start, 2)}")
    print(f"  Start of year qty:           {qty_start}")
    print(f"  End of year PMAVG (EUR):     {round(pmavg_end, 2)}")
    print(f"  End of year qty:             {qty_end}")
    print(f"  Carry file:                  {carry_out}")
    print(f"\n  E1kv:")
    print(f"    Kennzahl 994 (gains):      {round(total_gains, 2)} EUR")
    print(f"    Kennzahl 892 (losses):     {round(total_losses, 2)} EUR")
    print(f"    Net realized P/L:          {sign}{round(net, 2)} EUR")


def main():
    args = parse_args()

    if args.audit_format == "csv" and not args.audit_output:
        print("ERROR: --audit-output prefix required when --audit-format=csv")
        sys.exit(1)

    current_year = datetime.today().year

    print(f"\nDetecting earliest date in CSV files...")
    start_year = detect_start_year(args.broker_csv, args.equity_csv)
    print(f"Earliest year found: {start_year}")
    print(f"\nProcessing {start_year} -> {current_year}")
    print(f"Symbol: {args.symbol}\n")

    pmavg = Decimal("0")
    qty = Decimal("0")

    for year in range(start_year, current_year + 1):
        pmavg_start = pmavg
        qty_start = qty

        print(f"\n--- Processing {year} ---")

        audit_out = None
        if args.audit_format == "csv":
            audit_out = f"{args.audit_output}_{args.symbol}_{year}.csv"

        try:
            pmavg, qty, audit_logs = run_single_year(
                taxyear=year,
                symbol=args.symbol,
                broker_csv=args.broker_csv,
                equity_csv=args.equity_csv,
                pmavg_start=pmavg_start,
                qty_start=qty_start,
                audit_format=args.audit_format,
                audit_output=audit_out,
            )
        except Exception as e:
            print(f"  [!] Error processing {year}: {e}")
            sys.exit(1)

        carry_out = f"carry_{args.symbol}_{year}.json"
        save_carry(carry_out, year, args.symbol, pmavg, qty)

        print_year_summary(year, pmavg_start, qty_start, pmavg, qty, audit_logs, carry_out)

    print(f"\n{'='*60}")
    print(f"  Current position (as of today)")
    print(f"{'='*60}")
    print(f"  Shares held:       {qty}")
    print(f"  PMAVG cost basis:  {round(pmavg, 2)} EUR/share")
    print(f"  Total cost basis:  {round(pmavg * qty, 2)} EUR")


if __name__ == "__main__":
    main()

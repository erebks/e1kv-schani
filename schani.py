import argparse
from datetime import datetime
import sys
import json
from pathlib import Path

from core import *


def parse_args():
    p = argparse.ArgumentParser(description="E1kv Schani")

    p.add_argument("--taxyear", type=int, required=True)
    p.add_argument("--symbol", type=str, required=True)

    p.add_argument("--broker-csv", required=True)
    p.add_argument("--equity-csv", required=True)

    p.add_argument(
        "--carry-init",
        action="store_true",
        help="Initialize PMAVG/QTY carry (use on first year)",
    )

    p.add_argument("--carry-file", help="Path to carry-forward JSON file")

    p.add_argument(
        "--audit-format",
        choices=["human", "csv"],
        default="human",
    )

    p.add_argument(
        "--audit-output", help="Path to audit CSV (required if audit-format=csv)"
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


def load_carry(path: str, expected_year: int, symbol: str):
    p = Path(path)

    if not p.exists():
        raise ValueError(f"Carry file not found: {path}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    carry_year = data["taxyear"]
    carry_symbol = data.get("symbol")

    if carry_symbol != symbol:
        raise ValueError(f"Carry symbol mismatch: {carry_symbol} != {symbol}")

    if carry_year != expected_year - 1:
        raise ValueError(
            f"Carry year mismatch: expected {expected_year - 1}, got {carry_year}"
        )

    return D(data["pmavg"]), D(data["qty"])


def save_carry(path: str, taxyear: int, symbol: str, pmavg: Decimal, qty: Decimal):
    data = {
        "taxyear": taxyear,
        "symbol": symbol,
        "pmavg": str(pmavg),
        "qty": str(qty),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    args = parse_args()

    if args.audit_format == "csv" and not args.audit_output:
        print("ERROR: --audit-output required when --audit-format=csv")
        sys.exit(1)

    year_start = datetime(args.taxyear, 1, 1)
    year_end = datetime(args.taxyear, 12, 31)

    fx = FXRates(year_start, year_end)

    events = []
    events += parse_equity_award_csv(args.equity_csv, args.symbol, fx, args.taxyear)
    events += parse_brokerage_csv(args.broker_csv, args.symbol, fx, args.taxyear)

    if args.carry_file and args.carry_init:
        print(
            f"Arguments --carry-init and --carry-file provided. Use one or the other!"
        )
        sys.exit(1)

    if args.carry_init:
        pmavg_start = Decimal("0")
        qty_start = Decimal("0")

    if args.carry_file:
        pmavg_start, qty_start = load_carry(args.carry_file, args.taxyear, args.symbol)

    pmavg_end, qty_end, realized_pl, audit_logs = process_events_with_audit(
        events,
        pmavg_start=pmavg_start,
        qty_start=qty_start,
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

    carry_out = f"carry_{args.symbol}_{args.taxyear}.json"

    save_carry(
        carry_out,
        args.taxyear,
        args.symbol,
        pmavg_end,
        qty_end,
    )

    print(f"\nYear {args.taxyear} summary:")
    print(f"\tStart of year PMAVG (EUR): {round(pmavg_start, 2)}")
    print(f"\tStart of year stock quantity: {qty_start}")
    print(f"\tEnd of year PMAVG (EUR): {round(pmavg_end, 2)}")
    print(f"\tEnd of year stock quantity: {qty_end}")
    print(f"\tCarry file written to '{carry_out}'")
    print(f"\tRealized P/L (EUR): {round(realized_pl, 2)}")

    print("\nE1kv:")
    print(f"\tKennzahl 994: {round(total_gains, 2)}")
    print(f"\tKennzahl 892: {round(total_losses, 2)}")


if __name__ == "__main__":
    main()

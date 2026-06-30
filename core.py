from dataclasses import dataclass
from datetime import datetime, timedelta
import csv
from typing import List, Tuple, Optional
import requests
from decimal import Decimal, getcontext, ROUND_HALF_UP

# ---- Decimal config ----
getcontext().prec = 28


def D(x) -> Decimal:
    return Decimal(str(x))


def round_eur(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FXRates:
    def __init__(self, start_date: datetime, end_date: datetime):
        self.rates = self._load_rates(start_date, end_date)

    def _load_rates(self, start_date, end_date):
        url = (
            f"https://api.frankfurter.dev/v1/"
            f"{start_date.date()}..{end_date.date()}"
            f"?base=USD&symbols=EUR"
        )
        data = requests.get(url).json()["rates"]

        return {
            datetime.strptime(d, "%Y-%m-%d").date(): D(v["EUR"])
            for d, v in data.items()
        }

    def rate_on(self, date: datetime) -> Decimal:
        """ECB rule: use last available previous rate"""
        d = date.date()
        while d not in self.rates:
            d -= timedelta(days=1)
        return self.rates[d]


@dataclass
class AuditLog:
    date: datetime
    event_type: str

    qty: Decimal
    unit_price_usd: Decimal
    fx_rate: Decimal
    unit_price_eur: Decimal

    qty_before: Decimal
    pmavg_before: Decimal

    qty_after: Decimal
    pmavg_after: Decimal

    proceeds_eur: Optional[Decimal] = None
    cost_basis_eur: Optional[Decimal] = None
    realized_pl_eur: Optional[Decimal] = None


@dataclass
class Event:
    date: datetime
    type: str
    qty: Decimal
    price: Decimal
    price_eur: Decimal
    fx_rate: Decimal
    fees: Decimal = Decimal("0")
    fees_eur: Decimal = Decimal("0")


def parse_money(value: str) -> Decimal:
    if not value:
        return Decimal("0")
    return Decimal(value.replace("$", "").replace(",", "").strip())


def parse_schwab_date(value: str) -> datetime:
    # Schwab sometimes formats the Date as "MM/DD/YYYY as of MM/DD/YYYY"
    # (posting date vs. settlement/effective date). Use the posting date.
    value = value.split(" as of ")[0].strip()
    return datetime.strptime(value, "%m/%d/%Y")


def parse_equity_award_csv(
    path: str, symbol: str, fx: FXRates, taxyear: int
) -> list[Event]:
    events = []
    pending_lapse = None

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            if row.get("Action") == "Lapse":
                if row.get("Symbol") != symbol:
                    print(f"Symbol mismatch. Ignoring row '{row}'")
                    continue

                pending_lapse = row
                continue

            if pending_lapse and row.get("FairMarketValuePrice"):
                date = datetime.strptime(pending_lapse["Date"], "%m/%d/%Y")
                # Ignore lapses outside tax year
                if date.year != taxyear:
                    pending_lapse = None
                    continue

                usd_price = parse_money(row["FairMarketValuePrice"])
                eur_price = usd_price * fx.rate_on(date)

                events.append(
                    Event(
                        date=date,
                        type="lapse",
                        qty=D(pending_lapse["Quantity"].replace(",", "")),
                        price=usd_price,
                        price_eur=eur_price,
                        fx_rate=fx.rate_on(date),
                    )
                )
                pending_lapse = None
                continue

            # If we land here, raise exception! We're at risk of reporting something wrong
            s = f"Unhandled row in equity center parsing. Row: '{row}'"
            raise ValueError(s)

    return events


def parse_brokerage_csv(
    path: str, symbol: str, fx: FXRates, taxyear: int
) -> list[Event]:
    events = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            date = parse_schwab_date(row["Date"])
            # Skip transactions outside taxyear
            if date.year != taxyear:
                continue

            if (
                row.get("Action") == "MoneyLink Transfer"
                or row.get("Action") == "Stock Plan Activity"
                or row.get("Action") == "Journal"
                or row.get("Action") == "Wire Sent"
                or row.get("Action") == "NRA Tax Adj"
                or row.get("Action") == "Adjustment"
                or row.get("Action") == "Service Fee"
            ):
                # We can safely ignore those (cash/interest-tax items, no shares)
                continue
            elif row.get("Action") == "Credit Interest":
                # Todo: I guess this one should be relevant for Kennziffer 861?
                continue
            elif row.get("Action") == "Sell":
                if row.get("Symbol") != symbol:
                    print(f"Symbol mismatch. Ignoring row '{row}'")
                    continue

                usd_price = parse_money(row["Price"])
                eur_price = usd_price * fx.rate_on(date)
                usd_fees = parse_money(row.get("Fees & Comm"))
                eur_fees = usd_fees * fx.rate_on(date)

                events.append(
                    Event(
                        date=date,
                        type="sell",
                        qty=D(row["Quantity"].replace(",", "")),
                        price=usd_price,
                        price_eur=eur_price,
                        fx_rate=fx.rate_on(date),
                        fees=usd_fees,
                        fees_eur=eur_fees,
                    )
                )
            elif row.get("Action") == "Buy":
                if row.get("Symbol") != symbol:
                    print(f"Symbol mismatch. Ignoring row '{row}'")
                    continue

                usd_price = parse_money(row["Price"])
                eur_price = usd_price * fx.rate_on(date)
                usd_fees = parse_money(row.get("Fees & Comm"))
                eur_fees = usd_fees * fx.rate_on(date)

                events.append(
                    Event(
                        date=date,
                        type="buy",
                        qty=D(row["Quantity"].replace(",", "")),
                        price=usd_price,
                        price_eur=eur_price,
                        fx_rate=fx.rate_on(date),
                        fees=usd_fees,
                        fees_eur=eur_fees,
                    )
                )
            else:
                # If we land here, raise exception! We're at risk of reporting something wrong
                s = f"Unhandled row in brokerage parsing. Row: '{row}'"
                raise ValueError(s)

    return events


def process_events_with_audit(
    events: List[Event],
    pmavg_start: Decimal,
    qty_start: Decimal,
) -> Tuple[Decimal, Decimal, Decimal, List[AuditLog]]:

    pmavg = pmavg_start
    qty = qty_start
    realized_pl_total = Decimal("0")
    audit_logs: List[AuditLog] = []

    for e in sorted(events, key=lambda x: x.date):
        qty_before = qty
        pmavg_before = pmavg

        if e.type == "lapse":
            acquisition_value = e.price_eur * e.qty
            total_cost = pmavg * qty + acquisition_value

            qty += e.qty
            pmavg = total_cost / qty

            audit_logs.append(
                AuditLog(
                    date=e.date,
                    event_type="LAPSE",
                    qty=e.qty,
                    unit_price_usd=e.price,
                    unit_price_eur=e.price_eur,
                    fx_rate=e.fx_rate,
                    qty_before=qty_before,
                    pmavg_before=pmavg_before,
                    qty_after=qty,
                    pmavg_after=pmavg,
                    cost_basis_eur=acquisition_value,
                )
            )

        if e.type == "buy":
            acquisition_value = e.price_eur * e.qty
            total_cost = pmavg * qty + acquisition_value

            qty += e.qty
            pmavg = total_cost / qty

            audit_logs.append(
                AuditLog(
                    date=e.date,
                    event_type="BUY",
                    qty=e.qty,
                    unit_price_usd=e.price,
                    unit_price_eur=e.price_eur,
                    fx_rate=e.fx_rate,
                    qty_before=qty_before,
                    pmavg_before=pmavg_before,
                    qty_after=qty,
                    pmavg_after=pmavg,
                    cost_basis_eur=acquisition_value,
                )
            )

        elif e.type == "sell":
            proceeds = e.price_eur * e.qty
            cost_basis = pmavg * e.qty
            realized_pl = proceeds - cost_basis

            realized_pl_total += realized_pl
            qty -= e.qty

            if qty < 0:
                raise ValueError("Sold more shares than owned")

            audit_logs.append(
                AuditLog(
                    date=e.date,
                    event_type="SELL",
                    qty=e.qty,
                    unit_price_usd=e.price,
                    unit_price_eur=e.price_eur,
                    fx_rate=e.fx_rate,
                    qty_before=qty_before,
                    pmavg_before=pmavg_before,
                    qty_after=qty,
                    pmavg_after=pmavg,  # unchanged on sell
                    proceeds_eur=proceeds,
                    cost_basis_eur=cost_basis,
                    realized_pl_eur=realized_pl,
                )
            )

    return pmavg, qty, realized_pl_total, audit_logs


def export_audit_csv(audit_logs: list[AuditLog], path: str):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(AuditLog.__dataclass_fields__.keys())

        for log in audit_logs:
            writer.writerow(vars(log).values())

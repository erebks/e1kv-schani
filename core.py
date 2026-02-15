from dataclasses import dataclass
from datetime import datetime, timedelta
import csv
from typing import List, Tuple, Optional
import requests


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

        # normalize to datetime -> float
        rates = {
            datetime.strptime(d, "%Y-%m-%d").date(): v["EUR"] for d, v in data.items()
        }
        return dict(sorted(rates.items()))

    def rate_on(self, date: datetime) -> float:
        """ECB rule: use last available previous rate"""
        d = date.date()
        while d not in self.rates:
            d -= timedelta(days=1)
        return self.rates[d]


@dataclass
class AuditLog:
    date: datetime
    event_type: str

    qty: float
    unit_price_eur: float
    fx_rate: float

    qty_before: float
    pmavg_before: float

    qty_after: float
    pmavg_after: float

    proceeds_eur: Optional[float] = None
    cost_basis_eur: Optional[float] = None
    realized_pl_eur: Optional[float] = None


@dataclass
class Event:
    date: datetime
    type: str
    qty: float
    price: float  # EUR
    fx_rate: float
    fees: float = 0.0


def parse_money(value: str) -> float:
    if not value:
        return 0.0
    return float(value.replace("$", "").replace(",", ".").strip())


def parse_equity_award_csv(path: str, symbol: str, fx: FXRates, taxyear: int) -> list[Event]:
    events = []
    pending_lapse = None

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            if row.get("Action") == "Lapse":
                if row.get("Symbol") != symbol:
                    raise ValueError(
                        "For now this script only supports a single trade symbol"
                    )

                date = datetime.strptime(row["Date"], "%m/%d/%Y")

                # Ignore lapses outside tax year
                if date.year != taxyear:
                    pending_lapse = None
                    continue

                pending_lapse = row
                continue

            if pending_lapse and row.get("FairMarketValuePrice"):
                date = datetime.strptime(pending_lapse["Date"], "%m/%d/%Y")
                usd_price = parse_money(row["FairMarketValuePrice"])
                eur_price = usd_price * fx.rate_on(date)

                events.append(
                    Event(
                        date=date,
                        type="lapse",
                        qty=float(pending_lapse["Quantity"]),
                        price=eur_price,
                        fx_rate=fx.rate_on(date),
                    )
                )
                pending_lapse = None

    return events


def parse_brokerage_csv(path: str, symbol: str, fx: FXRates, taxyear: int) -> list[Event]:
    events = []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=",")

        for row in reader:
            if row.get("Action") != "Sell":
                continue

            if row.get("Symbol") != symbol:
                raise ValueError(
                    "For now this script only supports a single trade symbol"
                )

            date = datetime.strptime(row["Date"], "%m/%d/%Y")

            # Skip transactions outside taxyear
            if date.year != taxyear:
                continue

            eur_price = parse_money(row["Price"]) * fx.rate_on(date)
            eur_fees = parse_money(row.get("Fees & Comm")) * fx.rate_on(date)

            events.append(
                Event(
                    date=date,
                    type="sell",
                    qty=float(row["Quantity"]),
                    price=eur_price,
                    fx_rate=fx.rate_on(date),
                    fees=eur_fees,
                )
            )

    return events


from typing import List, Tuple


def process_events_with_audit(
    events: List[Event],
    pmavg_start: float,
    qty_start: float,
) -> Tuple[float, float, float, List[AuditLog]]:

    pmavg = pmavg_start
    qty = qty_start
    realized_pl_total = 0.0
    audit_logs: List[AuditLog] = []

    for e in sorted(events, key=lambda x: x.date):
        qty_before = qty
        pmavg_before = pmavg

        if e.type == "lapse":
            acquisition_value = e.price * e.qty
            total_cost = pmavg * qty + acquisition_value

            qty += e.qty
            pmavg = total_cost / qty

            audit_logs.append(
                AuditLog(
                    date=e.date,
                    event_type="LAPSE",
                    qty=e.qty,
                    unit_price_eur=e.price,
                    fx_rate=e.fx_rate,
                    qty_before=qty_before,
                    pmavg_before=pmavg_before,
                    qty_after=qty,
                    pmavg_after=pmavg,
                    cost_basis_eur=acquisition_value,
                )
            )

        elif e.type == "sell":
            proceeds = e.price * e.qty - e.fees
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
                    unit_price_eur=e.price,
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

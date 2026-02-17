# e1kv-schani
Your [Schani](https://de.wiktionary.org/wiki/Schani) for the Austrian E1kv tax reporting

# TL;DR
```bash
python schani.py \
  --taxyear 2024 \
  --symbol ASDF \
  --broker-csv Individual_Transactions.csv \
  --equity-csv EquityAwardsCenter.csv \
  --pmavg-start 0.0 \
  --qty-start 0 \
  --audit-format human
```

```bash
python schani.py \
  --taxyear 2024 \
  --symbol ASDF \
  --broker-csv Individual_Transactions.csv \
  --equity-csv EquityAwardsCenter.csv \
  --pmavg-start 0.0 \
  --qty-start 0 \
  --audit-format csv \
  --audit-output audit_2024.csv
```

# How it works

At its core, this tool consists of two main components:
1. CSV parsers that read the broker and equity award files and normalize all relevant transactions into a sequence of standardized events (e.g. lapse, sell, buy).
2. An event processor that processes these events in chronological order and calculates the realized profit or loss.

Under Austrian tax law, capital gains on shares must be calculated using the moving average cost method (["Gleitender Durchschnittspreisverfahren"](https://de.wikipedia.org/wiki/Gleitender_Durchschnittspreis)).
This means that, for each sale, the acquisition cost is determined based on the current moving average price.

To apply this method correctly, the tool requires the moving average price (`pmavg`) and the share quantity (`qty`) at the end of the previous tax year as input parameters.
With this approach, each tax year can be processed independently, without having to re-process the complete transaction history from the first acquisition onward.

If, at any point, the quantity of the relevant stock held is reduced to zero (either because it was never held or because all shares were sold), the moving average price (`pmavg`) is reset to zero.

# Where to get the documents?
Currently we only support exports from [Schwab](https://www.schwab.com/brokerage).
## Individual_Transactions.csv
* Navigate to Schwab and choose "Accounts" -> "Transaction History"
* Choose your "Individual" account (Blue drop-down list at the top left)
* Choose date range and download CSV
## EquityAwardsCenter.csv
* Navigate to Schwab and choose "Accounts" -> "Transaction History"
* Choose your "Equity Award Center" account (Blue drop-down list at the top left)
* Choose date range and download CSV

# Disclaimer
This script is provided for informational and personal use only.
It is based solely on my own understanding and interpretation of Austrian tax rules and publicly available information at the time of writing.

I make no representations or warranties of any kind, express or implied, regarding the correctness, completeness, accuracy, or suitability of the calculations or results produced by this script.

This script does not constitute tax advice, legal advice, financial advice, or professional advice of any kind.
It is not a substitute for consulting a qualified tax advisor, Steuerberater, lawyer, or other professional.

Use of this script is entirely at your own risk.
I expressly disclaim any liability for errors, omissions, or any consequences arising from the use of this script, including but not limited to incorrect tax filings, penalties, interest, or other financial or legal outcomes.

By using this script, you acknowledge and agree that:
- you are solely responsible for verifying all results, and
- you assume full responsibility for any actions taken based on its output.

## Sources
[findoc EStR 2000 20.2.4.12 Fremdwährungsgewinne](https://findok.bmf.gv.at/findok/volltext(suche:Standardsuche)?segmentId=103bf3f5-1cbd-4eed-861a-a179a74bb03b)

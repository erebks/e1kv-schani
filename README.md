# e1kv-schani
Helping you fill out the E1kv form for the Austrian capital gains tax reporting

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

# How to use
1. Get your CSVs from schwab
2. Set Pmavg (EUR) and stock quantity of the previous year (If it's your very first year, just use 0)
3. Run `schani.py`

# Where to get the documents?
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

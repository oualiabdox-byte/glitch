#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

printf '%s\n' "cTrader demo setup. Secrets are written only to .env and are not displayed."
read -r -p "cTrader Open API Client ID: " CLIENT_ID
printf '\n'
read -r -s -p "cTrader Open API Client Secret: " CLIENT_SECRET
printf '\n'
read -r -s -p "cTrader Demo Access Token: " ACCESS_TOKEN
printf '\n'
read -r -s -p "cTrader Refresh Token (optional): " REFRESH_TOKEN
printf '\n'
read -r -p "Demo account ID (press Enter to auto-detect): " ACCOUNT_ID
printf '\n'

if [[ -z "$CLIENT_ID" || -z "$CLIENT_SECRET" || -z "$ACCESS_TOKEN" ]]; then
  printf '%s\n' "Client ID, Client Secret, and Access Token are required." >&2
  exit 1
fi

umask 077
{
  printf 'CTRADER_CLIENT_ID=%s\n' "$CLIENT_ID"
  printf 'CTRADER_CLIENT_SECRET=%s\n' "$CLIENT_SECRET"
  printf 'CTRADER_ACCESS_TOKEN=%s\n' "$ACCESS_TOKEN"
  printf 'CTRADER_REFRESH_TOKEN=%s\n' "$REFRESH_TOKEN"
  printf 'CTRADER_ACCOUNT_ID=%s\n' "$ACCOUNT_ID"
  printf '\n'
  printf 'CTRADER_ENV=demo\n'
  printf 'CTRADER_PAIRS=EURUSD,GBPUSD,USDJPY,USDCHF,USDCAD,AUDUSD,NZDUSD\n'
  # These enable automatic trading on the cTrader DEMO endpoint only.
  printf 'CTRADER_ALLOW_ORDERS=true\n'
  printf 'CTRADER_DEMO_EXECUTE=true\n'
  printf 'CTRADER_DEMO_CONFIRM=I_UNDERSTAND_DEMO_TRADING\n'
  printf 'CTRADER_RUN_UNTIL_TRADE=true\n'
  printf 'CTRADER_POLL_SECONDS=300\n'
  printf 'CTRADER_DIAGNOSTICS_PATH=results/demo_diagnostics.jsonl\n'
  printf 'CTRADER_DATABASE_PATH=results/trading.db\n'
  printf 'CTRADER_STORAGE_LIMIT_MB=550\n'
  printf 'CTRADER_ORDER_VOLUME_UNITS=1000\n'
  printf 'CTRADER_MAX_ORDER_VOLUME_UNITS=1000\n'
  printf 'CTRADER_SVL_REQUIRE_ALIGNMENT=false\n'
  printf 'CTRADER_SVL_PROFILE_BINS=24\n'
  printf 'CTRADER_SVL_EQUAL_TOLERANCE_PCT=0.001\n'
  printf 'CTRADER_CONFIRM_LIVE=\n'
} > .env

unset CLIENT_ID CLIENT_SECRET ACCESS_TOKEN REFRESH_TOKEN ACCOUNT_ID
chmod 600 .env

printf '%s\n' "Created .env with automatic demo trading enabled."
printf '%s\n' "The runner refuses CTRADER_ENV=live."
printf '%s\n' "Run: PYTHONPATH=. python -m execution.demo_runner"

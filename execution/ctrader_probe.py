"""Minimal cTrader connectivity probe.

Usage:
  export CTRADER_CLIENT_ID='...'
  export CTRADER_CLIENT_SECRET='...'
  export CTRADER_ACCESS_TOKEN='...'
  export CTRADER_ENV=demo
  python -m execution.ctrader_probe

The probe authenticates the application and account, then requests account,
symbol and reconciliation state. It does not submit orders.
"""

from execution.ctrader_adapter import CTraderAdapter


def main() -> None:
    adapter = CTraderAdapter()
    adapter.assert_orders_disabled()
    print("[cTrader] configuration:", adapter.describe())
    adapter.connect()
    adapter.run()


if __name__ == "__main__":
    main()

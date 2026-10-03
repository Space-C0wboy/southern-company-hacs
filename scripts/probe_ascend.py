r"""One-off probe: does the Ascend (OCC) library fix (southern_company_api PR #24) work for this account?

Usage (Windows PowerShell, one line at a time):
    py -3.13 -m venv .venv
    .venv\Scripts\python -m pip install "git+https://github.com/sng492/southern_company_api@bcbaa10d509f7ebc767085d9682da05acbcfe1a7"
    .venv\Scripts\python scripts\probe_ascend.py USERNAME

Prompts for the password (never stored or printed). Logs in ONCE and stops at the
first failure — it never retries, so it can't trigger a lockout. Prints only
non-identifying results (account last-4, counts, kWh/$ figures).
"""
from __future__ import annotations

import asyncio
import datetime
import getpass
import sys

import aiohttp
from southern_company_api.parser import SouthernCompanyAPI


def step(name: str) -> None:
    print(f"... {name}", flush=True)


async def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    username = sys.argv[1]
    password = getpass.getpass("Southern Company password: ")

    async with aiohttp.ClientSession() as session:
        api = SouthernCompanyAPI(username, password, session)
        try:
            step("login (ScWebToken)")
            await api.authenticate()
            step("JWT exchange")
            jwt = await api.jwt
            print(f"OK: got JWT ({len(jwt)} chars)")

            step("accounts (Ascend)")
            accounts = await api.accounts
            print(f"OK: {len(accounts)} account(s)")
            for account in accounts:
                tail = account.number[-4:] if account.number else "????"
                print(f"  account ...{tail}: company={account.company.name} service_point={'yes' if account.service_point_number else 'NO'}")
                if not account.service_point_number:
                    continue

                step(f"month data ...{tail}")
                month = await account.get_month_data(jwt)
                print(f"  OK month: ${month.dollars_to_date:.2f} to date, {month.total_kwh_used:.1f} kWh, "
                      f"projected ${month.projected_bill_amount_low:.0f}-{month.projected_bill_amount_high:.0f}")

                end = datetime.datetime.now()
                start = end - datetime.timedelta(days=7)
                step(f"daily data ...{tail} (last 7 days)")
                days = await account.get_daily_data(start, end, jwt)
                print(f"  OK daily: {len(days)} rows; last = {days[-1] if days else 'none'}")

                step(f"hourly data ...{tail} (last 3 days)")
                hours = await account.get_hourly_data(end - datetime.timedelta(days=3), end, jwt)
                reported = [h for h in hours if h.usage]
                print(f"  OK hourly: {len(hours)} rows, {len(reported)} with usage")
        except Exception as err:  # report and stop; never retry
            print(f"FAIL at the step above: {type(err).__name__}: {str(err)[:300]}")
            return 1
    print("ALL OK: PR #24 works for this account.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

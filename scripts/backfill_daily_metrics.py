#!/usr/bin/env python3
"""Gecmis gunler icin tenant_daily_metrics upsert (tek seferlik / idempotent)."""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from database.daily_metrics import backfill_tenant_metrics  # noqa: E402


def main():
    p = argparse.ArgumentParser(description="tenant_daily_metrics backfill")
    p.add_argument("--tenant", type=int, default=None, help="Yalniz bu tenant_id")
    args = p.parse_args()
    n = backfill_tenant_metrics(args.tenant)
    print(f"[OK] {n} gun satiri islendi.")


if __name__ == "__main__":
    main()

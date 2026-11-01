"""Sol's separate fixed-scenario financial counterproof, not reviewer acceptance.

Uses hand-derived balance-sheet amounts and rational arithmetic; does not import
the main Python evaluator, Rust reducer, ledger state, or its NAV algorithm.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path


def check(report):
    rows = {r["day"]: r for r in report["daily"]}
    # Independent, fixed fixture: principal10000.00, buy100*10.00, fees0.31;
    # ex price9.58, gross42.00, tax8.40, sell100*9.58, fees0.78.
    gross = 100 * Fraction(42, 100) * 100
    withholding = gross * Fraction(1, 5)
    net = gross - withholding
    before_cash = 1_000_000 - 100*1000 - 31
    pre_ex = before_cash + 100*1000
    ex_assets = before_cash + 100*958 + gross - withholding
    after_sale_cash = before_cash + 100*958 - 78
    sale_assets = after_sale_cash + gross - withholding
    after_payment_cash = after_sale_cash + net
    assert (gross, withholding, net) == (4200, 840, 3360)
    assert rows[20260715]["nav_fen"] == pre_ex == 999_969
    assert rows[20260716]["cash_fen"] == before_cash == 899_969
    assert rows[20260716]["nav_fen"] == ex_assets == 999_129
    assert rows[20260716]["cash_dividend"]["receivable_fen"] == gross
    assert rows[20260716]["cash_dividend"]["liability_fen"] == withholding
    assert rows[20260717]["held_shares"] == 0
    assert rows[20260717]["cash_fen"] == after_sale_cash == 995_691
    assert rows[20260717]["nav_fen"] == sale_assets == 999_051
    assert rows[20260720]["cash_fen"] == after_payment_cash == sale_assets
    assert rows[20260720]["nav_fen"] == sale_assets
    assert report["ending_nav_fen"] == 1_000_000 - 4200 - 109 + 3360
    assert all(r["external_flow_total_fen"] == 0 for r in rows.values())
    assert len(report["fills"]) == 2 and report["total_fee_fen"] == 109
    # Counterexamples must disagree with the actual independently derived NAV.
    bad = dict(no_receivable=before_cash+100*958,
               ignore_tax=before_cash+100*958+gross,
               payment_double_profit=sale_assets+net,
               dividend_as_owner_deposit=1_000_000+net)
    assert bad["no_receivable"] != ex_assets
    assert bad["ignore_tax"] != ex_assets
    assert bad["payment_double_profit"] != after_payment_cash
    assert bad["dividend_as_owner_deposit"] != after_payment_cash
    return dict(kind="Sol separate hand-derived counterproof, not independent acceptance",
                status="PASS", gross_fen=int(gross), withholding_fen=int(withholding), net_fen=int(net),
                pre_ex_nav_fen=int(pre_ex), ex_nav_fen=int(ex_assets), after_sale_nav_fen=int(sale_assets),
                after_payment_nav_fen=int(after_payment_cash), false_models_rejected={k:int(v) for k,v in bad.items()})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(check(json.loads(a.report.read_bytes())), sort_keys=True))

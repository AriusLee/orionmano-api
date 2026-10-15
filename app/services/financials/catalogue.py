"""Line items, period labels and units for the confirmed-figures store.

Extraction (document_parser) emits `financial_data` keyed by statement and
line item, e.g. income_statement.cost_of_sales = {"FY2024": 1619}. The
catalogue maps those names onto one canonical key per line item, and says how
each feeds the valuation model's `historical_fs` arrays:

  hist_key — the historical_fs series it fills (None = shown and lockable,
             but not part of the 5-year model arrays)
  sign     — "as_is": keep the reported sign (profit can be a loss)
             "cost":  costs and liabilities are negative in historical_fs,
                      so the magnitude is written as a negative number
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LineItem:
    key: str
    label: str
    statement: str  # income_statement | balance_sheet | cash_flow
    hist_key: str | None
    sign: str  # as_is | cost
    aliases: tuple[str, ...] = ()


LINE_ITEMS: tuple[LineItem, ...] = (
    # Income statement
    LineItem("revenue", "Revenue", "income_statement", "revenue", "as_is", ("revenue", "turnover", "sales", "total_revenue")),
    LineItem("cogs", "Cost of sales", "income_statement", "cogs", "cost", ("cost_of_sales", "cost_of_revenue", "cost_of_goods_sold", "cogs")),
    LineItem("gross_profit", "Gross profit", "income_statement", "gross_profit", "as_is", ("gross_profit",)),
    LineItem("other_income", "Other income", "income_statement", "other_income_expense", "as_is", ("other_income", "other_income_expense", "other_gains")),
    LineItem("opex_total", "Operating / administrative expenses", "income_statement", "opex_total", "cost", ("administrative_expenses", "operating_expenses", "opex", "opex_total", "selling_general_administrative")),
    LineItem("ebitda", "EBITDA", "income_statement", "ebitda", "as_is", ("ebitda",)),
    LineItem("da", "Depreciation & amortisation", "income_statement", "da", "cost", ("depreciation_amortisation", "depreciation_and_amortisation", "depreciation_amortization", "depreciation", "da")),
    LineItem("ebit", "Operating profit (EBIT)", "income_statement", "ebit", "as_is", ("profit_from_operation", "profit_from_operations", "operating_profit", "ebit")),
    LineItem("interest_expense", "Finance costs", "income_statement", "interest_expense", "cost", ("finance_costs", "finance_cost", "interest_expense")),
    LineItem("profit_before_tax", "Profit before tax", "income_statement", "profit_before_tax", "as_is", ("profit_before_tax", "pbt")),
    LineItem("tax_expense", "Income tax", "income_statement", "tax_expense", "cost", ("taxation", "income_tax", "income_tax_expense", "tax_expense", "tax")),
    LineItem("net_income", "Net profit", "income_statement", "net_income", "as_is", ("net_income", "net_profit", "profit_for_the_year", "profit_after_tax")),
    # Balance sheet
    LineItem("cash", "Cash and bank balances", "balance_sheet", "cash", "as_is", ("cash", "cash_and_bank_balances", "cash_and_cash_equivalents")),
    LineItem("accounts_receivable", "Trade receivables", "balance_sheet", "accounts_receivable", "as_is", ("trade_receivables", "accounts_receivable", "trade_and_other_receivables")),
    LineItem("inventory", "Inventories", "balance_sheet", "inventory", "as_is", ("inventories", "inventory")),
    LineItem("contract_assets", "Contract assets", "balance_sheet", None, "as_is", ("contract_assets",)),
    LineItem("amount_due_from_related", "Amount due from related companies", "balance_sheet", None, "as_is", ("amount_due_from_related", "amount_due_from_related_company", "amount_due_from_related_companies")),
    LineItem("amount_due_from_shareholder", "Amount due from shareholder / director", "balance_sheet", None, "as_is", ("amount_due_from_shareholder", "amount_due_from_director")),
    LineItem("total_current_assets", "Total current assets", "balance_sheet", "total_current_assets", "as_is", ("current_assets", "total_current_assets")),
    LineItem("ppe", "Property, plant & equipment", "balance_sheet", "ppe", "as_is", ("property_plant_equipment", "property_plant_and_equipment", "ppe")),
    LineItem("right_of_use_assets", "Right-of-use assets", "balance_sheet", None, "as_is", ("right_of_use_assets",)),
    LineItem("total_assets", "Total assets", "balance_sheet", "total_assets", "as_is", ("total_assets",)),
    LineItem("accounts_payable", "Trade payables", "balance_sheet", "accounts_payable", "cost", ("trade_payables", "accounts_payable", "trade_and_other_payables")),
    LineItem("amount_due_to_related", "Amount due to related companies", "balance_sheet", None, "as_is", ("amount_due_to_related", "amount_due_to_related_company", "amount_due_to_related_companies")),
    LineItem("amount_due_to_shareholder", "Amount due to shareholder / director", "balance_sheet", None, "as_is", ("amount_due_to_shareholder", "amount_due_to_director")),
    LineItem("short_term_debt", "Short-term borrowings", "balance_sheet", "short_term_debt", "cost", ("short_term_debt", "short_term_borrowings")),
    LineItem("bank_borrowings", "Bank borrowings", "balance_sheet", None, "as_is", ("bank_borrowings", "borrowings")),
    LineItem("lease_liabilities", "Lease liabilities", "balance_sheet", None, "as_is", ("lease_liabilities",)),
    LineItem("income_tax_payable", "Income tax payable", "balance_sheet", None, "as_is", ("income_tax_payable", "tax_payable")),
    LineItem("total_current_liabilities", "Total current liabilities", "balance_sheet", "total_current_liabilities", "cost", ("current_liabilities", "total_current_liabilities")),
    LineItem("long_term_debt", "Long-term borrowings", "balance_sheet", "long_term_debt", "cost", ("long_term_debt", "long_term_borrowings")),
    LineItem("total_liabilities", "Total liabilities", "balance_sheet", "total_liabilities", "cost", ("total_liabilities",)),
    LineItem("share_capital", "Share capital", "balance_sheet", None, "as_is", ("share_capital",)),
    LineItem("retained_earnings", "Retained earnings", "balance_sheet", None, "as_is", ("retained_earnings", "retained_profits", "accumulated_profits")),
    LineItem("total_equity", "Total equity", "balance_sheet", "total_equity", "as_is", ("total_equity",)),
    # Cash flow
    LineItem("operating_cash_flow", "Net cash from operating activities", "cash_flow", None, "as_is", ("operating", "operating_cash_flow", "net_cash_from_operating_activities")),
    LineItem("investing_cash_flow", "Net cash used in investing activities", "cash_flow", None, "as_is", ("investing", "investing_cash_flow")),
    LineItem("financing_cash_flow", "Net cash from financing activities", "cash_flow", None, "as_is", ("financing", "financing_cash_flow")),
    LineItem("net_change_in_cash", "Net change in cash", "cash_flow", None, "as_is", ("net_change", "net_change_in_cash")),
)

BY_KEY: dict[str, LineItem] = {li.key: li for li in LINE_ITEMS}
_BY_ALIAS: dict[tuple[str, str], LineItem] = {
    (li.statement, alias): li for li in LINE_ITEMS for alias in (li.key, *li.aliases)
}
STATEMENTS = ("income_statement", "balance_sheet", "cash_flow")
STATEMENT_LABELS = {
    "income_statement": "Income statement",
    "balance_sheet": "Balance sheet",
    "cash_flow": "Cash flow",
}


def resolve(statement: str, raw_key: str) -> LineItem:
    """Canonical line item for an extracted (statement, key). Unknown keys keep
    their own name — they are stored and shown, but feed nothing."""
    k = re.sub(r"[^a-z0-9]+", "_", raw_key.strip().lower()).strip("_")
    hit = _BY_ALIAS.get((statement, k))
    if hit is not None:
        return hit
    return LineItem(k, k.replace("_", " ").capitalize(), statement, None, "as_is")


def item_for(key: str, statement: str | None = None) -> LineItem:
    hit = BY_KEY.get(key)
    if hit is not None:
        return hit
    return LineItem(key, key.replace("_", " ").capitalize(), statement or "income_statement", None, "as_is")


# ─── Periods ─────────────────────────────────────────────────────────────────

_INTERIM_TOKENS = (
    (re.compile(r"\b(?:h1|1h|first\s*half|six\s*months|6m)\b"), "H1"),
    (re.compile(r"\b(?:h2|2h|second\s*half)\b"), "H2"),
    (re.compile(r"\b(?:9m|nine\s*months)\b"), "9M"),
    (re.compile(r"\b(?:q1|1q)\b"), "Q1"),
    (re.compile(r"\b(?:q2|2q)\b"), "Q2"),
    (re.compile(r"\b(?:q3|3q|three\s*quarters)\b"), "Q3"),
    (re.compile(r"\b(?:q4|4q)\b"), "Q4"),
)


def normalize_period(label: str) -> tuple[str, str, int | None]:
    """("FY2024", "annual", 2024) from "FY2024", "FY 2024", "2024", "FYE2024",
    "31 Dec 2024"; ("H1_2025", "interim", 2025) from "H1_2025", "1H2025",
    "six months ended 30 Sep 2025". Anything else keeps its label, as interim."""
    raw = (label or "").strip()
    low = re.sub(r"[_\-]+", " ", raw.lower())
    # Split glued tokens like "1h2025" / "fy2024" / "h1 2025" for matching.
    spaced = re.sub(r"(?<=[a-z])(?=\d{4})|(?<=\d)(?=h\b)", " ", low)
    year_m = re.search(r"(19|20)\d{2}", low)
    year = int(year_m.group(0)) if year_m else None
    # "2023/24" or "2023/2024" is the year ending in 2024.
    split_m = re.search(r"((?:19|20)\d{2})\s*/\s*(\d{4}|\d{2})\b", low)
    if split_m:
        end = split_m.group(2)
        year = int(end) if len(end) == 4 else int(split_m.group(1)[:2] + end)
    for pattern, tag in _INTERIM_TOKENS:
        if pattern.search(spaced):
            return (f"{tag}_{year}" if year else raw.upper()), "interim", year
    if year is not None:
        return f"FY{year}", "annual", year
    return raw.upper() or "UNKNOWN", "interim", None


# ─── Units ───────────────────────────────────────────────────────────────────

def unit_multiplier(unit: str | None) -> float:
    """1000 for "'000", "thousands", "RM'000", "USD '000", "k"; 1e6 for
    "million(s)", "mm", "m", "'000,000"; 1e9 for billions; else 1."""
    if not unit:
        return 1.0
    u = unit.strip().lower().replace("’", "'")
    if re.search(r"billion|\bbn\b|'000,000,000", u):
        return 1e9
    if re.search(r"million|\bmm\b|\bmn\b|'000,000|\bm\b|\$m\b", u):
        return 1e6
    if re.search(r"thousand|'000|\b000\b|\bk\b|\$k\b", u):
        return 1e3
    return 1.0


def same_value(a: float | None, a_mult: float, b: float | None, b_mult: float) -> bool:
    """Equal once both are in actual units, allowing for rounding at the
    coarser of the two units (a figure in '000 vs one in units)."""
    if a is None or b is None:
        return a is None and b is None
    x, y = a * a_mult, b * b_mult
    tolerance = max(0.5 * max(a_mult, b_mult), 1e-6 * max(abs(x), abs(y)))
    return abs(x - y) <= tolerance


# ─── Currencies ──────────────────────────────────────────────────────────────

_CURRENCY_ALIASES = {
    "RM": "MYR", "RINGGIT": "MYR",
    "HK$": "HKD", "HK": "HKD",
    "US$": "USD", "$": "USD", "US": "USD",
    "S$": "SGD", "SG$": "SGD",
    "RMB": "CNY", "YUAN": "CNY",
    "NT$": "TWD", "A$": "AUD", "£": "GBP", "€": "EUR",
}


def normalize_currency(raw: str | None) -> str | None:
    """ISO code from what a statement prints: "RM" → MYR, "HK$'000" → HKD."""
    if not raw:
        return None
    s = raw.strip().upper()
    s = re.sub(r"['’]?0{3}.*$", "", s).strip()  # drop a unit glued on: HK$'000
    s = re.sub(r"\b(THOUSANDS?|MILLIONS?|BILLIONS?)\b", "", s).strip()
    if s in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[s]
    m = re.match(r"^([A-Z]{3})\b", s)
    if m:
        return m.group(1)
    for alias, code in _CURRENCY_ALIASES.items():
        if s.startswith(alias):
            return code
    return s[:8] or None


def parse_number(raw) -> float | None:
    """1234, "1,234", "(1,234)" → -1234, "-" / "" / "n/a" → None."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s or s in {"-", "—", "–"} or s.lower() in {"n/a", "na", "nil", "none", "null"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = re.sub(r"[^0-9.\-eE]", "", s.strip("()"))
    try:
        v = float(s)
    except ValueError:
        return None
    return -abs(v) if neg else v

"""
google_sheet_writer.py

Writes long-term scanner results to Google Sheets.
"""

from __future__ import annotations

import json
import os
from datetime import date

import gspread
from google.oauth2.service_account import Credentials


GOOGLE_SERVICE_ACCOUNT_JSON_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"

SPREADSHEET_ID = "1yxmvO8ohAxkVspojw8PZoc3PwV5OEcEGu7AMiTL-Njc"
RESULTS_WORKSHEET_NAME = "Scanner Results"


HEADERS = [
    "Run Date",
    "Ticker",
    "Sector",
    "Rating",
    "Action",
    "Total Score",
    "Quality Score",
    "Valuation Score",
    "Discount Score",
    "Technical Score",
    "Sentiment Label",
    "Sentiment Score",
    "Price",
    "PEG",
    "Forward PE",
    "Revenue Growth",
    "Gross Margin",
    "Free Cash Flow",
    "Top Headline 1",
    "Top Headline 2",
    "Top Headline 3",
    "Manual Decision",
    "Notes",
]


def _get_client():
    raw_json = os.getenv(GOOGLE_SERVICE_ACCOUNT_JSON_ENV)

    if not raw_json:
        print(f"Missing {GOOGLE_SERVICE_ACCOUNT_JSON_ENV}. Skipping Google Sheet write.")
        return None

    service_account_info = json.loads(raw_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]

    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=scopes,
    )

    return gspread.authorize(credentials)


def _get_or_create_worksheet(spreadsheet, title: str, rows: int = 1000, cols: int = 30):
    try:
        return spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def _safe(value):
    if value is None:
        return ""

    try:
        if isinstance(value, float):
            return round(value, 4)
    except Exception:
        pass

    return value


def _percent(value):
    if value is None:
        return ""

    try:
        return round(float(value) * 100, 2)
    except Exception:
        return value


def _number(value):
    if value is None:
        return ""

    try:
        return round(float(value), 2)
    except Exception:
        return value


def _headline(result, index: int) -> str:
    try:
        return result.headlines[index].get("title", "")
    except Exception:
        return ""


def result_to_row(result) -> list:
    fundamentals = result.fundamentals or {}

    return [
        date.today().isoformat(),
        result.ticker,
        fundamentals.get("sector", ""),
        result.rating,
        result.action,
        result.total_score,
        result.quality_score,
        result.valuation_score,
        result.discount_score,
        result.technical_score,
        result.sentiment_label,
        result.sentiment_score,
        result.price,
        _number(fundamentals.get("peg_ratio")),
        _number(fundamentals.get("forward_pe")),
        _percent(fundamentals.get("revenue_growth")),
        _percent(fundamentals.get("gross_margins")),
        _number(fundamentals.get("free_cashflow")),
        _headline(result, 0),
        _headline(result, 1),
        _headline(result, 2),
        "",
        "",
    ]


def write_scanner_results(results: list, clear_existing: bool = True):
    """
    Writes all scanner results to the Google Sheet.

    clear_existing=True means every run refreshes the sheet.
    Manual Decision and Notes will be cleared each run.
    Later, we can preserve those fields if needed.
    """
    client = _get_client()

    if client is None:
        return False

    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    worksheet = _get_or_create_worksheet(spreadsheet, RESULTS_WORKSHEET_NAME)

    rows = [HEADERS] + [result_to_row(result) for result in results]

    if clear_existing:
        worksheet.clear()

    worksheet.update(rows)

    print(f"Wrote {len(results)} scanner results to Google Sheet.")
    return True
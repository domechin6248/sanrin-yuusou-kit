"""
合同会社山林パートナーズ — Google スプレッドシート連携

サービスアカウント認証のみを使用する（公開リンクは使わない）。
認証ファイル: data/google_service_account.json
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = DATA_DIR / "sheets_config.json"


class SheetsConfigError(Exception):
    """設定・認証まわりのエラー。"""


def load_sheets_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SheetsConfigError(f"設定ファイルがありません: {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def credentials_path(config: dict[str, Any] | None = None) -> Path:
    cfg = config or load_sheets_config()
    name = cfg.get("credentials_file", "google_service_account.json")
    return DATA_DIR / name


def get_connection_status() -> dict[str, str]:
    """UI 表示用の接続状態。"""
    try:
        cfg = load_sheets_config()
    except SheetsConfigError as exc:
        return {"status": "error", "message": str(exc)}

    cred = credentials_path(cfg)
    if not cred.exists():
        return {
            "status": "missing_credentials",
            "message": (
                f"認証ファイルがありません: {cred.name}\n"
                "Google Cloud のサービスアカウント JSON を data/ に配置し、"
                "スプレッドシートをそのメールに「編集者」共有してください。"
            ),
        }
    try:
        with open(cred, encoding="utf-8") as f:
            info = json.load(f)
        email = info.get("client_email", "(不明)")
    except (json.JSONDecodeError, OSError) as exc:
        return {"status": "error", "message": f"認証ファイルを読めません: {exc}"}

    return {
        "status": "ready",
        "message": f"認証ファイルあり（{email}）",
        "service_account_email": email,
        "spreadsheet_id": cfg.get("spreadsheet_id", ""),
    }


def _authorize(config: dict[str, Any]):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise SheetsConfigError(
            "gspread / google-auth が未インストールです。"
            " pip install -r requirements.txt を実行してください。"
        ) from exc

    cred = credentials_path(config)
    if not cred.exists():
        raise SheetsConfigError(f"認証ファイルがありません: {cred}")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    credentials = Credentials.from_service_account_file(str(cred), scopes=scopes)
    return gspread.authorize(credentials)


def _open_worksheet(config: dict[str, Any]):
    gc = _authorize(config)
    spreadsheet_id = config.get("spreadsheet_id", "").strip()
    if not spreadsheet_id:
        raise SheetsConfigError("sheets_config.json に spreadsheet_id がありません")

    sh = gc.open_by_key(spreadsheet_id)
    gid = int(config.get("worksheet_gid", 0))
    for ws in sh.worksheets():
        if int(ws.id) == gid:
            return ws
    # gid 不一致時は先頭シート
    return sh.sheet1


def _parse_reception_date(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")
    # 2026/11/18 9:14 or 2026-11-18
    m = re.match(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", raw)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return raw[:10]


def _row_to_customer(row: dict[str, Any], columns: dict[str, str]) -> dict[str, str]:
    def col(key: str) -> str:
        header = columns.get(key, "")
        if not header:
            return ""
        val = row.get(header, "")
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        return str(val).strip()

    base = col("address")
    detail = col("address_detail")
    if base and detail and detail not in base:
        addr = f"{base}{detail}"
    else:
        addr = base or detail

    notes = col("notes")
    forest_owner = col("forest_owner")
    if forest_owner:
        extra = f"山林の名義: {forest_owner}"
        notes = f"{notes} / {extra}" if notes else extra

    return {
        "management_no": col("management_no"),
        "reception_date": _parse_reception_date(col("reception_datetime")),
        "name": col("name"),
        "honorific": "様",
        "phone": col("phone"),
        "postal_code": col("postal_code"),
        "address": addr,
        "notes": notes,
        "forest_location": "",
        "status": col("status"),
        "route": col("route"),
        "sheet_row": str(row.get("_sheet_row", "")),
    }


def fetch_customers(
    *,
    route_contains: str | None = None,
    status_filter: str | None = None,
) -> pd.DataFrame:
    """
    シート全行を取得し、アプリ用カラムに変換した DataFrame を返す。

    追加列: status, route, sheet_row（1始まりのシート行番号）
    """
    config = load_sheets_config()
    columns = config.get("columns", {})
    ws = _open_worksheet(config)
    records = ws.get_all_records()

    rows: list[dict[str, str]] = []
    for i, rec in enumerate(records):
        # ヘッダーが1行目 → データはシート行 2 から
        rec = {**rec, "_sheet_row": i + 2}
        customer = _row_to_customer(rec, columns)
        if not customer.get("management_no") and not customer.get("name"):
            continue
        if route_contains:
            if route_contains not in (customer.get("route") or ""):
                continue
        if status_filter and status_filter != "(すべて)":
            if (customer.get("status") or "") != status_filter:
                continue
        rows.append(customer)

    if not rows:
        return pd.DataFrame(
            columns=[
                "management_no",
                "reception_date",
                "name",
                "honorific",
                "phone",
                "postal_code",
                "address",
                "notes",
                "forest_location",
                "status",
                "route",
                "sheet_row",
            ]
        )
    return pd.DataFrame(rows)


def update_status(sheet_row: int, new_status: str | None = None) -> None:
    """指定行の「対応状況」列を更新する。"""
    config = load_sheets_config()
    columns = config.get("columns", {})
    status_header = columns.get("status", "対応状況")
    value = new_status or config.get("status_after_kit", "郵送キット作成済")

    ws = _open_worksheet(config)
    headers = ws.row_values(1)
    try:
        col_idx = headers.index(status_header) + 1
    except ValueError as exc:
        raise SheetsConfigError(f"列「{status_header}」が見つかりません") from exc

    ws.update_cell(int(sheet_row), col_idx, value)


def list_status_values(df: pd.DataFrame) -> list[str]:
    if df.empty or "status" not in df.columns:
        return []
    vals = sorted({str(v) for v in df["status"].tolist() if str(v).strip()})
    return vals

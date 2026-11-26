"""
合同会社山林パートナーズ
不要山林の有料引き取り事業 — 郵送キット自動生成システム

起動例（既存アプリと衝突しないポート）:
  streamlit run app.py --server.port 8510
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

import pandas as pd
import streamlit as st

from pdf_generator import (
    generate_common_documents_pdf,
    generate_labels_pdf,
    get_font_status,
)
from sheets_client import (
    SheetsConfigError,
    fetch_customers,
    get_connection_status,
    load_sheets_config,
    update_status,
)

# ---------------------------------------------------------------------------
# パス（本アプリ専用フォルダ内に完結）
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
FONTS_DIR = BASE_DIR / "fonts"
COMPANY_JSON = DATA_DIR / "company_info.json"
HISTORY_CSV = DATA_DIR / "history.csv"
COUNTER_JSON = DATA_DIR / "management_counter.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)

HISTORY_COLUMNS = [
    "management_no",
    "reception_date",
    "postal_code",
    "address",
    "name",
    "honorific",
    "phone",
    "forest_location",
    "notes",
    "saved_at",
]

DEFAULT_COMPANY = {
    "company_name": "合同会社山林パートナーズ",
    "department": "山林引き取り受付係",
    "postal_code": "895-0000",
    "address": "鹿児島県薩摩川内市〇〇町1-2-3",
    "phone": "0996-00-0000",
    "contact_person": "担当者名",
}


# ---------------------------------------------------------------------------
# データ I/O
# ---------------------------------------------------------------------------
def load_company_info() -> dict[str, str]:
    if COMPANY_JSON.exists():
        try:
            with open(COMPANY_JSON, encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULT_COMPANY, **data}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_COMPANY)


def save_company_info(info: dict[str, str]) -> None:
    with open(COMPANY_JSON, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)


def _next_management_no() -> str:
    """SP-YYYYMMDD-NNN 形式で自動採番。"""
    today = date.today().strftime("%Y%m%d")
    counter: dict[str, int] = {}
    if COUNTER_JSON.exists():
        try:
            with open(COUNTER_JSON, encoding="utf-8") as f:
                counter = json.load(f)
        except (json.JSONDecodeError, OSError):
            counter = {}
    seq = int(counter.get(today, 0)) + 1
    counter[today] = seq
    with open(COUNTER_JSON, "w", encoding="utf-8") as f:
        json.dump(counter, f, ensure_ascii=False, indent=2)
    return f"SP-{today}-{seq:03d}"


def peek_management_no() -> str:
    """採番せずに次番号のプレビューを返す。"""
    today = date.today().strftime("%Y%m%d")
    counter: dict[str, int] = {}
    if COUNTER_JSON.exists():
        try:
            with open(COUNTER_JSON, encoding="utf-8") as f:
                counter = json.load(f)
        except (json.JSONDecodeError, OSError):
            counter = {}
    seq = int(counter.get(today, 0)) + 1
    return f"SP-{today}-{seq:03d}"


def load_history() -> pd.DataFrame:
    if not HISTORY_CSV.exists():
        return pd.DataFrame(columns=HISTORY_COLUMNS)
    try:
        df = pd.read_csv(HISTORY_CSV, dtype=str).fillna("")
        for col in HISTORY_COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[HISTORY_COLUMNS]
    except Exception:  # noqa: BLE001
        return pd.DataFrame(columns=HISTORY_COLUMNS)


def append_history(row: dict[str, str]) -> None:
    df = load_history()
    new = {col: row.get(col, "") for col in HISTORY_COLUMNS}
    new["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
    df.to_csv(HISTORY_CSV, index=False, encoding="utf-8-sig")


def customer_from_inputs(
    *,
    postal_code: str,
    address: str,
    name: str,
    honorific: str,
    phone: str,
    management_no: str,
    reception_date: str,
    forest_location: str,
    notes: str,
) -> dict[str, str]:
    return {
        "postal_code": postal_code.strip(),
        "address": address.strip(),
        "name": name.strip(),
        "honorific": honorific.strip() or "様",
        "phone": phone.strip(),
        "management_no": management_no.strip(),
        "reception_date": reception_date,
        "forest_location": forest_location.strip(),
        "notes": notes.strip(),
    }


def safe_filename(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    return text.strip() or "noname"


DESKTOP_DIR = Path.home() / "Desktop"


def build_label_pdf(
    customer: dict[str, str],
    company: dict[str, str],
    *,
    label_mode: str,
    label_layout: str,
    offset_x: float,
    offset_y: float,
    show_guides: bool,
) -> dict[str, Any]:
    """封筒用宛名ラベルのみ生成する。"""
    labels_pdf = generate_labels_pdf(
        customer,
        company,
        mode=label_mode,
        layout=label_layout,
        offset_x_mm=offset_x,
        offset_y_mm=offset_y,
        show_guides=show_guides,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = safe_filename(f"{customer['management_no']}_{customer['name']}")
    (OUTPUT_DIR / f"{base_name}_宛名ラベル_{stamp}.pdf").write_bytes(labels_pdf)
    return {
        "labels": labels_pdf,
        "base_name": base_name,
        "management_no": customer["management_no"],
    }


def save_common_documents_to_desktop(company: dict[str, str]) -> list[Path]:
    """共通資料をカタカナ宛名用・漢字宛名用の2種類、デスクトップへ保存。"""
    DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    variants = [
        ("kana", "カタカナ宛名用"),
        ("kanji", "漢字宛名用"),
    ]
    paths: list[Path] = []
    for style, label in variants:
        pdf = generate_common_documents_pdf(company, name_style=style)
        path = DESKTOP_DIR / f"山林パートナーズ_郵送キット_共通資料_{label}.pdf"
        path.write_bytes(pdf)
        (OUTPUT_DIR / path.name).write_bytes(pdf)
        paths.append(path)
    return paths


def render_download_buttons(key_prefix: str = "main") -> None:
    if "last_pdfs" not in st.session_state:
        return
    pdfs = st.session_state["last_pdfs"]
    st.subheader("ダウンロード（封筒用宛名ラベル）")
    st.download_button(
        "【長3封筒用】宛名ラベルPDF",
        data=pdfs["labels"],
        file_name=f"{pdfs['base_name']}_宛名ラベル.pdf",
        mime="application/pdf",
        use_container_width=True,
        key=f"{key_prefix}_dl_labels",
    )


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="山林パートナーズ 郵送キット",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _app_password() -> str | None:
    """Secrets に app_password があれば返す（クラウド用）。"""
    try:
        return str(st.secrets["app_password"])
    except Exception:  # noqa: BLE001
        return None


def require_login() -> bool:
    """
    app_password が設定されているときだけログインを要求する。
    ローカルで Secrets 未設定ならスキップ（開発用）。
    """
    expected = _app_password()
    if not expected:
        return True
    if st.session_state.get("sanrin_mail_kit_authenticated"):
        return True

    st.title("🌲 山林パートナーズ　郵送キット")
    st.caption("社内利用のためパスワードが必要です")
    with st.form("sanrin_mail_kit_login"):
        pw = st.text_input("パスワード", type="password")
        submitted = st.form_submit_button("ログイン", type="primary")
    if submitted:
        if pw == expected:
            st.session_state["sanrin_mail_kit_authenticated"] = True
            st.rerun()
        st.error("パスワードが違います")
    return False


if not require_login():
    st.stop()

st.title("🌲 山林パートナーズ　郵送キット自動生成")
st.caption(
    "合同会社山林パートナーズ｜不要山林の有料引き取り事業｜"
    "封筒用宛名ラベル生成｜同封文書は共通資料（デスクトップへ保存）｜ポート 8510"
)



# --- サイドバー：自社情報・フォント・印刷設定 ---
with st.sidebar:
    st.header("自社情報（返信用）")
    company = load_company_info()

    company_name = st.text_input("社名", value=company["company_name"])
    department = st.text_input("部署・係名", value=company["department"])
    co_postal = st.text_input("郵便番号", value=company["postal_code"])
    co_address = st.text_area("住所", value=company["address"], height=70)
    co_phone = st.text_input("電話番号", value=company["phone"])
    contact_person = st.text_input("担当者名", value=company["contact_person"])

    company_edited = {
        "company_name": company_name.strip(),
        "department": department.strip(),
        "postal_code": co_postal.strip(),
        "address": co_address.strip(),
        "phone": co_phone.strip(),
        "contact_person": contact_person.strip(),
    }

    if st.button("自社情報を保存", use_container_width=True):
        save_company_info(company_edited)
        st.success("data/company_info.json に保存しました")

    st.divider()
    st.header("共通資料（同封文書）")
    st.caption("カタカナ宛名用／漢字宛名用の2種類をデスクトップに保存します。")
    if st.button("共通資料をデスクトップへ保存（2種類）", use_container_width=True):
        try:
            paths = save_common_documents_to_desktop(company_edited)
            st.success("保存しました：\n" + "\n".join(str(p) for p in paths))
        except Exception as exc:  # noqa: BLE001
            st.error(f"保存に失敗しました: {exc}")

    st.divider()
    st.header("宛名ラベル印刷設定")
    label_mode = st.radio(
        "印刷モード",
        options=["C", "A", "B"],
        format_func=lambda m: {
            "C": "長3封筒貼付用（95×55mm・推奨）",
            "A": "モードA：A4ノーカット（上下2分割）",
            "B": "モードB：市販マルチラベル（2面/4面）",
        }[m],
        index=0,
    )
    label_layout = "2面"
    if label_mode == "B":
        label_layout = st.selectbox("ラベル面数", ["2面", "4面"], index=0)

    offset_x = st.slider(
        "左右オフセット（mm）",
        min_value=-10.0,
        max_value=10.0,
        value=0.0,
        step=0.5,
        help="右方向がプラス",
    )
    offset_y = st.slider(
        "上下オフセット（mm）",
        min_value=-10.0,
        max_value=10.0,
        value=0.0,
        step=0.5,
        help="上方向がプラス",
    )
    show_guides = st.checkbox("枠線を表示する（テスト印刷用）", value=True)

    st.divider()
    st.header("スプレッドシート連携")
    sheets_status = get_connection_status()
    if sheets_status["status"] == "ready":
        st.success("認証ファイル OK")
        st.caption(sheets_status["message"])
    elif sheets_status["status"] == "missing_credentials":
        st.warning("認証ファイル未配置")
        st.caption(sheets_status["message"])
    else:
        st.error(sheets_status["message"])

    st.divider()
    st.header("日本語フォント")
    font_status = get_font_status()
    if font_status["status"] == "OK":
        st.success("フォント検出 OK")
        st.caption(f"通常: {font_status['regular']}")
        st.caption(f"太字: {font_status['bold']}")
    else:
        st.error(font_status["status"])
        st.caption(
            "fonts/ に NotoSansJP-Regular.ttf および "
            "NotoSansJP-Bold.ttf を配置してください。"
        )


# --- メイン：タブ ---
tab_sheets, tab_single, tab_history, tab_csv = st.tabs(
    [
        "① スプレッドシートから選択",
        "② 単件作成",
        "③ 履歴・再読み込み",
        "④ CSV一括生成",
    ]
)

# ===================================================================
# タブ① スプレッドシートから選択
# ===================================================================
with tab_sheets:
    st.subheader("スプレッドシートからお客様を選択")
    st.caption(
        "サービスアカウント経由で読み込みます（公開リンクは使いません）。"
        "個人情報が含まれるため、シート共有はサービスアカウントのみにしてください。"
    )

    filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
    with filter_col1:
        only_yusou = st.checkbox("案内ルートが「郵送」のものだけ", value=True)
    with filter_col2:
        status_choice = st.selectbox(
            "対応状況フィルタ",
            options=["(すべて)", "未発送", "郵送キット作成済", "HP案内済み"],
            index=1,
        )
    with filter_col3:
        load_btn = st.button("シートを読み込む", type="primary", use_container_width=True)

    if load_btn:
        try:
            df = fetch_customers(
                route_contains="郵送" if only_yusou else None,
                status_filter=None if status_choice == "(すべて)" else status_choice,
            )
            # 対応状況の実データも含めて再フィルタ用に全件キャッシュ
            all_df = fetch_customers(
                route_contains="郵送" if only_yusou else None,
                status_filter=None,
            )
            st.session_state["sheets_df"] = df
            st.session_state["sheets_all_for_status"] = all_df
            st.success(f"{len(df)} 件読み込みました")
        except SheetsConfigError as exc:
            st.error(str(exc))
        except Exception as exc:  # noqa: BLE001
            st.error(f"シート読み込みに失敗しました: {exc}")

    sheets_df: pd.DataFrame = st.session_state.get(
        "sheets_df", pd.DataFrame()
    )
    if sheets_df is not None and not sheets_df.empty:
        # 表示用に絞り込み再適用（セッション内）
        view = sheets_df.copy()
        if only_yusou:
            view = view[view["route"].astype(str).str.contains("郵送", na=False)]
        if status_choice != "(すべて)":
            view = view[view["status"].astype(str) == status_choice]

        display_cols = [
            "management_no",
            "name_kanji",
            "name_kana",
            "name",
            "postal_code",
            "address",
            "phone",
            "reception_date",
            "status",
            "route",
        ]
        st.dataframe(
            view[[c for c in display_cols if c in view.columns]],
            use_container_width=True,
            hide_index=True,
        )

        if view.empty:
            st.info("条件に一致する行がありません。フィルタを変更して再読み込みしてください。")
        else:
            options = [
                f"{r.management_no} | {r.name} | {r.status} | {r.address}"
                for r in view.itertuples()
            ]
            selected = st.selectbox("PDFを作成するお客様", options=options)
            sel_idx = options.index(selected)
            selected_row = view.iloc[sel_idx].to_dict()

            b1, b2 = st.columns(2)
            with b1:
                if st.button("フォームに読み込む", use_container_width=True):
                    st.session_state.preset_customer = {
                        k: selected_row.get(k, "")
                        for k in HISTORY_COLUMNS
                        if k != "saved_at"
                    }
                    st.session_state.preset_customer["sheet_row"] = selected_row.get(
                        "sheet_row", ""
                    )
                    st.session_state.form_reset_token = (
                        st.session_state.get("form_reset_token", 0) + 1
                    )
                    st.success("② 単件作成タブに読み込みました。")
            with b2:
                if st.button(
                    "この内容で宛名ラベルを生成する",
                    type="primary",
                    use_container_width=True,
                ):
                    customer = customer_from_inputs(
                        postal_code=str(selected_row.get("postal_code", "")),
                        address=str(selected_row.get("address", "")),
                        name=str(selected_row.get("name", "")),
                        honorific=str(selected_row.get("honorific", "様") or "様"),
                        phone=str(selected_row.get("phone", "")),
                        management_no=str(selected_row.get("management_no", "")),
                        reception_date=str(
                            selected_row.get("reception_date", date.today().isoformat())
                        ),
                        forest_location=str(selected_row.get("forest_location", "")),
                        notes=str(selected_row.get("notes", "")),
                    )
                    if not customer["name"] or not customer["address"]:
                        st.error("氏名または住所が空です。シートの内容を確認してください。")
                    else:
                        append_history(customer)
                        save_company_info(company_edited)
                        st.session_state["last_pdfs"] = build_label_pdf(
                            customer,
                            company_edited,
                            label_mode=label_mode,
                            label_layout=label_layout,
                            offset_x=offset_x,
                            offset_y=offset_y,
                            show_guides=show_guides,
                        )
                        st.success(
                            f"宛名ラベルを生成しました（{customer['management_no']}）。"
                        )
                        # 対応状況を書き戻し
                        sheet_row = selected_row.get("sheet_row", "")
                        if sheet_row:
                            try:
                                cfg = load_sheets_config()
                                new_status = cfg.get(
                                    "status_after_kit", "郵送キット作成済"
                                )
                                update_status(int(sheet_row), new_status)
                                st.info(
                                    f"スプレッドシートの対応状況を「{new_status}」に更新しました。"
                                )
                            except Exception as exc:  # noqa: BLE001
                                st.warning(f"対応状況の書き戻しに失敗しました: {exc}")

    elif sheets_status["status"] != "ready":
        st.info(
            "先に `data/google_service_account.json` を配置し、"
            "スプレッドシートをサービスアカウントに共有してください（README 参照）。"
        )

    render_download_buttons("sheets")


# ===================================================================
# タブ② 単件作成
# ===================================================================
with tab_single:
    st.subheader("お客様情報（往信先）")

    if "mgmt_preview" not in st.session_state:
        st.session_state.mgmt_preview = peek_management_no()
    if "form_reset_token" not in st.session_state:
        st.session_state.form_reset_token = 0

    # 履歴・Sheets から読み込んだ値があればプリセット
    preset: dict[str, Any] = st.session_state.get("preset_customer", {})

    col1, col2 = st.columns(2)
    with col1:
        postal_code = st.text_input(
            "郵便番号",
            value=preset.get("postal_code", ""),
            placeholder="895-0000",
            key=f"postal_{st.session_state.form_reset_token}",
        )
        address = st.text_area(
            "住所",
            value=preset.get("address", ""),
            placeholder="鹿児島県薩摩川内市〇〇町1-2-3",
            height=80,
            key=f"address_{st.session_state.form_reset_token}",
        )
        name = st.text_input(
            "お客様氏名",
            value=preset.get("name", ""),
            placeholder="山田 太郎",
            key=f"name_{st.session_state.form_reset_token}",
        )
        honorific = st.text_input(
            "敬称",
            value=preset.get("honorific", "様"),
            key=f"honorific_{st.session_state.form_reset_token}",
        )
    with col2:
        phone = st.text_input(
            "電話番号（任意）",
            value=preset.get("phone", ""),
            placeholder="090-0000-0000",
            key=f"phone_{st.session_state.form_reset_token}",
        )
        reception_date = st.date_input(
            "受付日",
            value=(
                date.fromisoformat(preset["reception_date"])
                if preset.get("reception_date")
                else date.today()
            ),
            key=f"date_{st.session_state.form_reset_token}",
        )
        auto_mgmt = st.checkbox(
            "管理番号を自動採番する",
            value=not bool(preset.get("management_no")),
            key=f"auto_mgmt_{st.session_state.form_reset_token}",
        )
        if auto_mgmt:
            st.info(f"採番予定：`{st.session_state.mgmt_preview}`（PDF生成時に確定）")
            management_no_input = st.session_state.mgmt_preview
        else:
            management_no_input = st.text_input(
                "管理番号",
                value=preset.get("management_no", st.session_state.mgmt_preview),
                key=f"mgmt_{st.session_state.form_reset_token}",
            )

    st.subheader("事前ヒアリング内容（任意・書類へ事前印字）")
    forest_location = st.text_input(
        "対象山林の所在地（市町村・大字など）",
        value=preset.get("forest_location", ""),
        placeholder="鹿児島県○○市△△町□□",
        key=f"forest_{st.session_state.form_reset_token}",
    )
    notes = st.text_area(
        "特記事項・備考",
        value=preset.get("notes", ""),
        height=70,
        key=f"notes_{st.session_state.form_reset_token}",
    )

    st.divider()
    gen_col1, gen_col2, gen_col3 = st.columns([1, 1, 1])
    with gen_col1:
        do_generate = st.button(
            "📄 宛名ラベルを生成する", type="primary", use_container_width=True
        )
    with gen_col2:
        save_only = st.button("履歴に保存のみ", use_container_width=True)
    with gen_col3:
        if st.button("入力をクリア", use_container_width=True):
            st.session_state.preset_customer = {}
            st.session_state.form_reset_token += 1
            st.session_state.mgmt_preview = peek_management_no()
            st.rerun()

    if do_generate or save_only:
        if not name.strip() or not address.strip():
            st.error("お客様氏名と住所は必須です。")
        else:
            if auto_mgmt and do_generate:
                management_no = _next_management_no()
                st.session_state.mgmt_preview = peek_management_no()
            elif auto_mgmt and save_only:
                management_no = _next_management_no()
                st.session_state.mgmt_preview = peek_management_no()
            else:
                management_no = management_no_input.strip()

            customer = customer_from_inputs(
                postal_code=postal_code,
                address=address,
                name=name,
                honorific=honorific,
                phone=phone,
                management_no=management_no,
                reception_date=reception_date.isoformat(),
                forest_location=forest_location,
                notes=notes,
            )

            # 履歴保存
            append_history(customer)
            save_company_info(company_edited)

            if save_only and not do_generate:
                st.success(f"履歴に保存しました（管理番号：{management_no}）")
            else:
                st.session_state["last_pdfs"] = build_label_pdf(
                    customer,
                    company_edited,
                    label_mode=label_mode,
                    label_layout=label_layout,
                    offset_x=offset_x,
                    offset_y=offset_y,
                    show_guides=show_guides,
                )
                # Sheets から読み込んだ行なら対応状況を更新
                sheet_row = preset.get("sheet_row", "")
                if sheet_row and do_generate:
                    try:
                        cfg = load_sheets_config()
                        new_status = cfg.get("status_after_kit", "郵送キット作成済")
                        update_status(int(sheet_row), new_status)
                        st.info(
                            f"スプレッドシートの対応状況を「{new_status}」に更新しました。"
                        )
                    except Exception as exc:  # noqa: BLE001
                        st.warning(f"対応状況の書き戻しに失敗しました: {exc}")
                st.success(
                    f"宛名ラベルを生成しました（管理番号：{management_no}）。"
                    f"同封文書はサイドバーから共通資料をデスクトップへ保存してください。"
                )

    render_download_buttons("single")


# ===================================================================
# タブ③ 履歴
# ===================================================================
with tab_history:
    st.subheader("保存履歴")
    history_df = load_history()
    if history_df.empty:
        st.info("まだ履歴がありません。単件作成で PDF 生成または保存を行うとここに表示されます。")
    else:
        st.dataframe(history_df, use_container_width=True, hide_index=True)

        st.download_button(
            "履歴CSVをダウンロード",
            data=history_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="sanrin_mail_kit_history.csv",
            mime="text/csv",
        )

        options = [
            f"{r.management_no} | {r.name} | {r.reception_date}"
            for r in history_df.itertuples()
        ]
        selected = st.selectbox("再読み込みする履歴を選択", options=options)
        if st.button("選択した履歴をフォームに読み込む", type="primary"):
            idx = options.index(selected)
            row = history_df.iloc[idx].to_dict()
            st.session_state.preset_customer = row
            st.session_state.form_reset_token += 1
            st.success("② 単件作成タブに読み込みました。タブを切り替えて確認してください。")

        st.divider()
        st.caption("履歴から再生成")
        if st.button("選択した履歴で PDF を再生成"):
            idx = options.index(selected)
            row = history_df.iloc[idx].to_dict()
            customer = customer_from_inputs(
                postal_code=row.get("postal_code", ""),
                address=row.get("address", ""),
                name=row.get("name", ""),
                honorific=row.get("honorific", "様"),
                phone=row.get("phone", ""),
                management_no=row.get("management_no", ""),
                reception_date=row.get("reception_date", date.today().isoformat()),
                forest_location=row.get("forest_location", ""),
                notes=row.get("notes", ""),
            )
            st.session_state["last_pdfs"] = build_label_pdf(
                customer,
                company_edited,
                label_mode=label_mode,
                label_layout=label_layout,
                offset_x=offset_x,
                offset_y=offset_y,
                show_guides=show_guides,
            )
            st.success("再生成しました。各タブ下部のダウンロードボタンをご利用ください。")
        render_download_buttons("history")


# ===================================================================
# タブ④ CSV一括生成
# ===================================================================
with tab_csv:
    st.subheader("CSV一括生成")
    st.markdown(
        """
CSV の列名（ヘッダー）は以下を想定しています。

| 列名 | 必須 | 説明 |
|------|------|------|
| `postal_code` | | 郵便番号 |
| `address` | ✓ | 住所 |
| `name` | ✓ | お客様氏名 |
| `honorific` | | 敬称（省略時「様」） |
| `phone` | | 電話番号 |
| `management_no` | | 管理番号（空なら自動採番） |
| `reception_date` | | 受付日 `YYYY-MM-DD`（空なら今日） |
| `forest_location` | | 対象山林の所在地 |
| `notes` | | 特記事項 |
"""
    )

    # テンプレートダウンロード
    template_buf = StringIO()
    writer = csv.DictWriter(template_buf, fieldnames=[c for c in HISTORY_COLUMNS if c != "saved_at"])
    writer.writeheader()
    writer.writerow(
        {
            "management_no": "",
            "reception_date": date.today().isoformat(),
            "postal_code": "895-0000",
            "address": "鹿児島県薩摩川内市〇〇町1-2-3",
            "name": "山田 太郎",
            "honorific": "様",
            "phone": "090-0000-0000",
            "forest_location": "鹿児島県○○市△△町",
            "notes": "",
        }
    )
    st.download_button(
        "CSVテンプレートをダウンロード",
        data=template_buf.getvalue().encode("utf-8-sig"),
        file_name="sanrin_mail_kit_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("CSVファイルをアップロード", type=["csv"])
    if uploaded is not None:
        try:
            raw = uploaded.read()
            try:
                text = raw.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw.decode("cp932")
            batch_df = pd.read_csv(StringIO(text), dtype=str).fillna("")
        except Exception as exc:  # noqa: BLE001
            st.error(f"CSVの読み込みに失敗しました: {exc}")
            batch_df = None

        if batch_df is not None and not batch_df.empty:
            st.write(f"**{len(batch_df)} 件** 読み込みました")
            st.dataframe(batch_df, use_container_width=True, hide_index=True)

            if st.button("一括で PDF を生成する", type="primary"):
                zip_buf = BytesIO()
                ok_count = 0
                errors: list[str] = []
                with ZipFile(zip_buf, "w") as zf:
                    for i, row in batch_df.iterrows():
                        row_dict = row.to_dict()
                        cname = str(row_dict.get("name", "")).strip()
                        caddr = str(row_dict.get("address", "")).strip()
                        if not cname or not caddr:
                            errors.append(f"行 {i + 2}: 氏名または住所が空のためスキップ")
                            continue

                        mgmt = str(row_dict.get("management_no", "")).strip()
                        if not mgmt:
                            mgmt = _next_management_no()

                        recv = str(row_dict.get("reception_date", "")).strip()
                        if not recv:
                            recv = date.today().isoformat()

                        customer = customer_from_inputs(
                            postal_code=str(row_dict.get("postal_code", "")),
                            address=caddr,
                            name=cname,
                            honorific=str(row_dict.get("honorific", "様") or "様"),
                            phone=str(row_dict.get("phone", "")),
                            management_no=mgmt,
                            reception_date=recv,
                            forest_location=str(row_dict.get("forest_location", "")),
                            notes=str(row_dict.get("notes", "")),
                        )
                        append_history(customer)
                        pdfs = build_label_pdf(
                            customer,
                            company_edited,
                            label_mode=label_mode,
                            label_layout=label_layout,
                            offset_x=offset_x,
                            offset_y=offset_y,
                            show_guides=show_guides,
                        )
                        zf.writestr(f"{pdfs['base_name']}_宛名ラベル.pdf", pdfs["labels"])
                        ok_count += 1

                zip_buf.seek(0)
                st.success(f"{ok_count} 件の PDF を生成しました。")
                if errors:
                    for e in errors:
                        st.warning(e)
                st.download_button(
                    "一括PDF（ZIP）をダウンロード",
                    data=zip_buf.getvalue(),
                    file_name=f"sanrin_mail_kit_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                )
                st.session_state.mgmt_preview = peek_management_no()

"""
合同会社山林パートナーズ — 郵送キット PDF 生成モジュール
同封書類（送付状・ヒアリングシート）および宛名ラベルを生成する。
"""

from __future__ import annotations

import os
import platform
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ---------------------------------------------------------------------------
# パス・定数
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
FONTS_DIR = BASE_DIR / "fonts"

PAGE_W, PAGE_H = A4  # 210mm × 297mm

FONT_REGULAR = "SanrinJP"
FONT_BOLD = "SanrinJP-Bold"

RED = colors.Color(0.75, 0.05, 0.05)
DARK = colors.Color(0.15, 0.15, 0.15)
GRAY = colors.Color(0.45, 0.45, 0.45)
LIGHT_GRAY = colors.Color(0.85, 0.85, 0.85)


# ---------------------------------------------------------------------------
# 日本語フォント検出・登録
# ---------------------------------------------------------------------------
def _candidate_font_paths() -> list[tuple[Path, Path | None]]:
    """(regular, bold|None) の候補リストを返す。"""
    candidates: list[tuple[Path, Path | None]] = []

    # 1) アプリ同梱 fonts/
    local_regular = [
        FONTS_DIR / "NotoSansJP-Regular.ttf",
        FONTS_DIR / "NotoSansCJKjp-Regular.otf",
        FONTS_DIR / "ipaexg.ttf",
        FONTS_DIR / "IPAexGothic.ttf",
        FONTS_DIR / "GenShinGothic-Regular.ttf",
        FONTS_DIR / "SourceHanSans-Regular.otf",
    ]
    local_bold = [
        FONTS_DIR / "NotoSansJP-Bold.ttf",
        FONTS_DIR / "NotoSansCJKjp-Bold.otf",
        FONTS_DIR / "GenShinGothic-Bold.ttf",
        FONTS_DIR / "SourceHanSans-Bold.otf",
        FONTS_DIR / "NotoSansJP-Regular.ttf",  # 太字ファイルが無い場合のフォールバック
    ]
    for reg in local_regular:
        if reg.exists():
            bold = next((b for b in local_bold if b.exists()), reg)
            candidates.append((reg, bold))

    system = platform.system()
    if system == "Darwin":
        mac_fonts = [
            (
                Path("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"),
                Path("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"),
            ),
            (
                Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
                Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
            ),
            (
                Path("/Library/Fonts/Arial Unicode.ttf"),
                Path("/Library/Fonts/Arial Unicode.ttf"),
            ),
            (
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            ),
        ]
        # AppleGothic / Osaka 等
        for name in ("AppleGothic.ttf", "Osaka.ttf"):
            p = Path("/System/Library/Fonts") / name
            if p.exists():
                mac_fonts.append((p, p))
            p2 = Path("/Library/Fonts") / name
            if p2.exists():
                mac_fonts.append((p2, p2))
        candidates.extend(mac_fonts)

    elif system == "Windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        fonts = windir / "Fonts"
        win_fonts = [
            (fonts / "msgothic.ttc", fonts / "msgothic.ttc"),
            (fonts / "meiryo.ttc", fonts / "meiryo.ttc"),
            (fonts / "YuGothM.ttc", fonts / "YuGothB.ttc"),
            (fonts / "YuGothR.ttc", fonts / "YuGothB.ttc"),
            (fonts / "msmincho.ttc", fonts / "msmincho.ttc"),
        ]
        candidates.extend(win_fonts)

    else:
        # Linux 等
        linux_fonts = [
            (
                Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
                Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
            ),
            (
                Path("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"),
                Path("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf"),
            ),
            (
                Path("/usr/share/fonts/truetype/noto/NotoSansCJKjp-Regular.otf"),
                Path("/usr/share/fonts/truetype/noto/NotoSansCJKjp-Bold.otf"),
            ),
        ]
        candidates.extend(linux_fonts)

    return candidates


_fonts_registered = False
_font_info: dict[str, str] = {"regular": "", "bold": "", "status": "未登録"}


def get_font_status() -> dict[str, str]:
    """現在登録されているフォント情報を返す。"""
    ensure_fonts()
    return dict(_font_info)


def ensure_fonts() -> None:
    """日本語フォントを検出し、ReportLab に登録する。"""
    global _fonts_registered, _font_info
    if _fonts_registered:
        return

    for regular, bold in _candidate_font_paths():
        if not regular.exists():
            continue
        try:
            # TTC は subfontIndex=0 で試行
            if regular.suffix.lower() == ".ttc":
                pdfmetrics.registerFont(
                    TTFont(FONT_REGULAR, str(regular), subfontIndex=0)
                )
            else:
                pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular)))

            bold_path = bold if bold and bold.exists() else regular
            bold_name = FONT_BOLD
            try:
                if bold_path.suffix.lower() == ".ttc":
                    pdfmetrics.registerFont(
                        TTFont(bold_name, str(bold_path), subfontIndex=0)
                    )
                else:
                    pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
            except Exception:
                # 太字が失敗したら通常フォントを太字名でも登録
                if bold_path.suffix.lower() == ".ttc":
                    pdfmetrics.registerFont(
                        TTFont(bold_name, str(regular), subfontIndex=0)
                    )
                else:
                    pdfmetrics.registerFont(TTFont(bold_name, str(regular)))

            _font_info = {
                "regular": str(regular),
                "bold": str(bold_path),
                "status": "OK",
            }
            _fonts_registered = True
            return
        except Exception as exc:  # noqa: BLE001
            _font_info = {
                "regular": str(regular),
                "bold": "",
                "status": f"失敗: {exc}",
            }
            continue

    # フォールバック: Helvetica（日本語は化けるがクラッシュ防止）
    _font_info = {
        "regular": "(Helvetica — 日本語非対応)",
        "bold": "(Helvetica-Bold)",
        "status": "日本語フォント未検出。./fonts/ に NotoSansJP-Regular.ttf 等を配置してください。",
    }
    # 名前だけ登録しておかないと描画時にエラーになるため、標準フォント名をエイリアス化はできない。
    # 呼び出し側で FONT_REGULAR が未登録なら Helvetica を使う。
    _fonts_registered = True


def _font(bold: bool = False) -> str:
    ensure_fonts()
    name = FONT_BOLD if bold else FONT_REGULAR
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    return "Helvetica-Bold" if bold else "Helvetica"


# ---------------------------------------------------------------------------
# 描画ヘルパー
# ---------------------------------------------------------------------------
def _draw_wrapped_text(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str,
    font_size: float,
    leading: float | None = None,
    color: Any = DARK,
    align: str = "left",
) -> float:
    """テキストを折り返して描画し、最終 Y 座標を返す。"""
    leading = leading or font_size * 1.4
    c.setFont(font_name, font_size)
    c.setFillColor(color)
    lines = _wrap_text(text, font_name, font_size, max_width)
    for i, line in enumerate(lines):
        yy = y - i * leading
        if align == "center":
            c.drawCentredString(x + max_width / 2, yy, line)
        elif align == "right":
            c.drawRightString(x + max_width, yy, line)
        else:
            c.drawString(x, yy, line)
    return y - (len(lines) - 1) * leading if lines else y


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    if not text:
        return [""]
    # 改行を尊重
    paragraphs = text.replace("\r\n", "\n").split("\n")
    result: list[str] = []
    for para in paragraphs:
        if not para:
            result.append("")
            continue
        current = ""
        for ch in para:
            trial = current + ch
            if pdfmetrics.stringWidth(trial, font_name, font_size) <= max_width:
                current = trial
            else:
                if current:
                    result.append(current)
                current = ch
        if current:
            result.append(current)
    return result or [""]


def _fit_font_size(
    text: str,
    font_name: str,
    max_width: float,
    max_size: float,
    min_size: float = 7.0,
) -> float:
    size = max_size
    while size > min_size:
        if pdfmetrics.stringWidth(text, font_name, size) <= max_width:
            return size
        size -= 0.5
    return min_size


def _draw_checkbox_line(
    c: canvas.Canvas,
    x: float,
    y: float,
    label: str,
    font_size: float = 11,
    box_size: float = 12,
    max_width: float | None = None,
) -> float:
    """大きなチェックボックス付き行を描画。戻り値は次の Y。"""
    c.setStrokeColor(DARK)
    c.setLineWidth(1.2)
    c.rect(x, y - 2, box_size, box_size, stroke=1, fill=0)
    # 空のチェック記号風
    c.setFont(_font(), font_size * 0.7)
    c.setFillColor(GRAY)
    # ラベル
    text_x = x + box_size + 6
    width = (max_width or (PAGE_W - text_x - 20 * mm))
    final_y = _draw_wrapped_text(
        c, label, text_x, y + 1, width, _font(), font_size, leading=font_size * 1.45
    )
    lines = _wrap_text(label, _font(), font_size, width)
    return min(final_y, y) - font_size * 1.45 * max(0, len(lines) - 1) - 10


def _draw_emphasized(
    c: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_size: float = 10,
) -> float:
    """赤字・太字の強調テキスト。"""
    return _draw_wrapped_text(
        c, text, x, y, max_width, _font(True), font_size, color=RED
    )


# ---------------------------------------------------------------------------
# 同封書類 PDF（共通資料：お客様名・住所は印字しない）
# ---------------------------------------------------------------------------
def generate_common_documents_pdf(company: dict) -> bytes:
    """送付状兼お手続きガイド + 簡易ヒアリングシート（共通・手書き欄あり）。"""
    ensure_fonts()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_cover_letter_common(c, company)
    c.showPage()
    _draw_hearing_sheet_common(c, company)
    c.save()
    return buf.getvalue()


def generate_documents_pdf(customer: dict, company: dict) -> bytes:
    """互換用。共通資料を返す（顧客名は印字しない）。"""
    return generate_common_documents_pdf(company)


def _draw_cover_letter_common(c: canvas.Canvas, company: dict) -> None:
    """共通の送付状。宛名・管理番号は空欄（手書き／ラベルで対応）。"""
    margin = 16 * mm
    y = PAGE_H - 16 * mm
    body = _font(True)

    c.setFont(body, 12)
    c.setFillColor(DARK)
    c.drawRightString(PAGE_W - margin, y, company.get("company_name", ""))
    y -= 16
    c.setFont(body, 11)
    c.drawRightString(
        PAGE_W - margin,
        y,
        f"〒{company.get('postal_code', '')}  {company.get('address', '')}",
    )
    y -= 14
    phone = company.get("phone", "")
    dept = company.get("department", "")
    contact = company.get("contact_person", "")
    right_line = "  /  ".join(filter(None, [dept, f"TEL {phone}" if phone else "", contact]))
    if right_line:
        c.drawRightString(PAGE_W - margin, y, right_line)

    y -= 12
    c.setStrokeColor(DARK)
    c.setLineWidth(1.5)
    c.line(margin, y, PAGE_W - margin, y)

    y -= 28
    c.setFont(body, 14)
    c.setFillColor(DARK)
    c.drawString(margin, y, "お客様　各位")

    y -= 34
    c.setStrokeColor(DARK)
    c.setFillColor(colors.Color(0.95, 0.95, 0.93))
    title_h = 32
    c.roundRect(margin, y - 6, PAGE_W - 2 * margin, title_h, 3, stroke=1, fill=1)
    c.setFont(body, 17)
    c.setFillColor(DARK)
    c.drawCentredString(PAGE_W / 2, y + 4, "土地引き取りご相談　郵送お手続きのご案内")

    y -= 36
    intro = (
        "このたびは土地の引き取りについてお問い合わせいただき、誠にありがとうございます。"
        "パソコン操作がご不安な方も安心してご利用いただけるよう、郵送キットをお届けしました。"
        "下記をご確認のうえ、同封の返信用封筒でご返送ください。"
    )
    y = _draw_wrapped_text(
        c, intro, margin, y, PAGE_W - 2 * margin, body, 13, leading=20
    )

    y -= 28
    c.setFont(body, 15)
    c.setFillColor(DARK)
    c.drawString(margin, y, "■　ご返送いただきたいもの")
    y -= 10
    c.setStrokeColor(DARK)
    c.setLineWidth(1.2)
    c.line(margin, y, PAGE_W - margin, y)

    y -= 20
    tip = (
        "【ひとこと】　「どの土地・物件を引き取りたいか」が分かる書類のコピーが必要です。"
        "市区町村から届く固定資産税の書類や、市役所・町村役場で取得できる証明書などです。"
        "お手元の書類の名前が違っても構いません。どれか1種類で大丈夫です。"
    )
    tip_h = 58
    c.setFillColor(colors.Color(0.96, 0.98, 1.0))
    c.setStrokeColor(DARK)
    c.setLineWidth(0.9)
    c.roundRect(margin, y - tip_h, PAGE_W - 2 * margin, tip_h, 2, stroke=1, fill=1)
    _draw_wrapped_text(
        c, tip, margin + 8, y - 14, PAGE_W - 2 * margin - 16, body, 12, leading=18
    )
    y -= tip_h + 22

    items = [
        (
            "①　土地・物件の内容が分かる書類のコピー（どれか1つでOK）",
            (
                "例）固定資産税の納税通知書・課税明細書／名寄せ帳（固定資産課税台帳の写し）／"
                "固定資産公課証明書／評価証明書 など。"
                "所在地・地番・地目（山林・原野・畑・宅地など）・面積が載っているページをコピーしてください。"
                "※ 原本は送らず、必ずコピーをお送りください。"
            ),
        ),
        (
            "②　ご本人様確認書類のコピー",
            (
                "運転免許証の両面、またはマイナンバーカードの表面のみ。"
                "※ マイナンバーカードの裏面は絶対にコピーしないでください。"
            ),
        ),
        (
            "③　同封の「土地引き取り　簡易ヒアリングシート」（ご記入のうえ）",
            None,
        ),
    ]
    content_w = PAGE_W - 2 * margin - 22
    for label, emphasis in items:
        box = 16
        c.setStrokeColor(DARK)
        c.setLineWidth(1.5)
        c.setFillColor(colors.white)
        c.rect(margin, y - 2, box, box, stroke=1, fill=1)

        text_x = margin + box + 10
        y = _draw_wrapped_text(
            c, label, text_x, y + 2, content_w - box, body, 13.5, leading=19
        )
        if emphasis:
            y -= 16
            y = _draw_wrapped_text(
                c,
                emphasis,
                text_x,
                y,
                content_w - box,
                body,
                12,
                leading=18,
                color=RED if "※" in emphasis else DARK,
            )
        y -= 22

    y -= 10
    c.setFont(body, 15)
    c.setFillColor(DARK)
    c.drawString(margin, y, "■　今後の流れ")
    y -= 10
    c.setStrokeColor(DARK)
    c.setLineWidth(1.2)
    c.line(margin, y, PAGE_W - margin, y)

    y -= 22
    flow = (
        "書類が弊社に到着してから、原則として1週間以内に、"
        "内容を確認のうえお見積り・今後のご案内をご連絡いたします。"
        "どの書類を送ればよいか迷われた場合も、お気軽にお電話ください。"
    )
    _draw_wrapped_text(
        c, flow, margin, y, PAGE_W - 2 * margin, body, 13, leading=20
    )

    c.setFont(body, 10)
    c.setFillColor(GRAY)
    c.drawCentredString(
        PAGE_W / 2,
        12 * mm,
        f"{company.get('company_name', '')}　｜　土地引き取りご相談 郵送キット（共通資料）",
    )


def _draw_hearing_sheet_common(c: canvas.Canvas, company: dict) -> None:
    """共通ヒアリングシート。連絡先は下部の手書き欄。"""
    margin = 16 * mm
    y = PAGE_H - 14 * mm
    body = _font(True)

    # 大きく目立たせる返送案内
    banner_h = 28
    c.setFillColor(colors.Color(0.85, 0.12, 0.12))
    c.setStrokeColor(colors.Color(0.85, 0.12, 0.12))
    c.roundRect(margin, y - 6, PAGE_W - 2 * margin, banner_h, 3, stroke=0, fill=1)
    c.setFont(body, 16)
    c.setFillColor(colors.white)
    c.drawCentredString(
        PAGE_W / 2,
        y + 2,
        "この用紙はご記入のうえ、他の書類と一緒に【必ずご返送ください】",
    )

    y -= 42
    c.setFillColor(colors.Color(0.95, 0.95, 0.93))
    c.setStrokeColor(DARK)
    c.setLineWidth(1.3)
    c.roundRect(margin, y - 8, PAGE_W - 2 * margin, 34, 3, stroke=1, fill=1)
    c.setFont(body, 17)
    c.setFillColor(DARK)
    c.drawCentredString(PAGE_W / 2, y, "土地引き取り　簡易ヒアリングシート")

    y -= 40
    c.setFont(body, 15)
    c.drawString(margin, y, "■　対象となる土地・物件の指定")
    y -= 8

    box_h = 118
    c.setStrokeColor(DARK)
    c.setLineWidth(1.1)
    c.setFillColor(colors.Color(1, 0.97, 0.97))
    c.roundRect(margin, y - box_h, PAGE_W - 2 * margin, box_h, 2, stroke=1, fill=1)

    guide = (
        "同封いただく固定資産の書類（課税明細書・名寄せ帳・公課証明書など）のコピーの中で、"
        "引き取りをご希望される土地・物件の行（所在地の左側または地番）に赤ペン等で丸（〇）をつけてください。"
    )
    _draw_wrapped_text(
        c,
        guide,
        margin + 10,
        y - 16,
        PAGE_W - 2 * margin - 20,
        body,
        12,
        leading=17,
        color=DARK,
    )

    # 所在地の左側に丸を付ける記入例（地番は隠さない）
    ex_y = y - 58
    c.setFont(body, 12)
    c.setFillColor(DARK)
    c.drawString(margin + 10, ex_y + 18, "【記入例】")

    # 簡易テーブル風の例（左に丸用の余白）
    mark_w = 28
    table_x = margin + 10 + mark_w
    table_w = PAGE_W - 2 * margin - 20 - mark_w
    col_w = [table_w * 0.34, table_w * 0.22, table_w * 0.16, table_w * 0.28]
    headers = ["所在地", "地番", "地目", "面積"]
    row1 = ["〇〇市△△町", "1234番", "山林", "2,500㎡"]
    row2 = ["〇〇市△△町", "56番7", "原野", "800㎡"]

    header_h = 18
    row_h = 22
    table_top = ex_y + 8
    c.setFillColor(colors.Color(0.92, 0.92, 0.90))
    c.setStrokeColor(DARK)
    c.setLineWidth(0.9)
    c.rect(table_x, table_top - header_h, table_w, header_h, stroke=1, fill=1)
    c.setFont(body, 11)
    c.setFillColor(DARK)
    hx = table_x
    for i, h in enumerate(headers):
        c.drawCentredString(hx + col_w[i] / 2, table_top - 13, h)
        hx += col_w[i]

    for ri, row in enumerate([row1, row2]):
        ry = table_top - header_h - (ri + 1) * row_h
        c.setFillColor(colors.white)
        c.setStrokeColor(DARK)
        c.rect(table_x, ry, table_w, row_h, stroke=1, fill=1)
        c.setFont(body, 11)
        c.setFillColor(DARK)
        cx = table_x
        for i, cell in enumerate(row):
            c.drawCentredString(cx + col_w[i] / 2, ry + 6, cell)
            cx += col_w[i]

    # 1行目・所在地の左側に赤丸＋「引き取り希望」ラベル
    mark_cx = table_x - mark_w / 2
    mark_cy = table_top - header_h - row_h / 2
    c.setStrokeColor(RED)
    c.setLineWidth(2.2)
    c.circle(mark_cx, mark_cy, 11, stroke=1, fill=0)
    c.setFont(body, 10)
    c.setFillColor(RED)
    c.drawCentredString(mark_cx, mark_cy + row_h + 2, "引き取り希望")

    c.setFont(body, 10)
    c.setFillColor(GRAY)
    c.drawString(
        margin + 10,
        y - box_h + 8,
        "※ 上の例のように、引き取りを希望する土地の所在地の左側（または地番）に丸をつけてください。",
    )

    y = y - box_h - 22

    c.setFont(body, 15)
    c.setFillColor(DARK)
    c.drawString(margin, y, "■　簡単なご質問（該当するものに ✓ をつけてください）")
    y -= 24

    questions = [
        (
            "１．名義について",
            ["単独名義", "共有名義", "相続未登記（名義変更前）"],
        ),
        (
            "２．境界の把握",
            ["だいたい分かる", "全く分からない"],
        ),
        (
            "３．土地・物件の状態",
            ["建物・工作物なし", "建物・小屋あり", "不明"],
        ),
        (
            "４．ご連絡希望の時間帯",
            ["午前中", "13〜17時", "17時以降", "いつでも可"],
        ),
    ]

    for q_title, options in questions:
        c.setFont(body, 14)
        c.setFillColor(DARK)
        c.drawString(margin, y, q_title)
        y -= 20
        opt_x = margin + 8
        for opt in options:
            box = 15
            c.setStrokeColor(DARK)
            c.setLineWidth(1.3)
            c.setFillColor(colors.white)
            c.rect(opt_x, y - 2, box, box, stroke=1, fill=1)
            c.setFont(body, 13)
            c.setFillColor(DARK)
            c.drawString(opt_x + box + 6, y, opt)
            opt_w = pdfmetrics.stringWidth(opt, body, 13) + box + 20
            opt_x += opt_w
            if opt_x > PAGE_W - margin - 55 * mm:
                opt_x = margin + 8
                y -= 20
        y -= 24

    c.setFont(body, 15)
    c.setFillColor(DARK)
    c.drawString(margin, y, "■　自由記入欄・ご質問欄")
    y -= 8

    free_h = 44
    c.setStrokeColor(DARK)
    c.setLineWidth(1.1)
    c.setFillColor(colors.white)
    c.rect(margin, y - free_h, PAGE_W - 2 * margin, free_h, stroke=1, fill=1)

    c.setStrokeColor(LIGHT_GRAY)
    c.setDash(2, 3)
    line_y = y - 20
    while line_y > y - free_h + 6:
        c.line(margin + 4, line_y, PAGE_W - margin - 4, line_y)
        line_y -= 18
    c.setDash()

    # 下部：ご連絡先（枠線なし・高めの記入ライン）
    y = y - free_h - 22
    c.setFont(body, 15)
    c.setFillColor(DARK)
    c.drawString(margin, y, "■　ご連絡先（ご記入ください）")
    y -= 16

    field_h = 34
    field_gap = 10
    label_w = 78
    fields = [
        ("お名前", True),
        ("ご住所", False),
        ("お電話番号", False),
    ]
    for label, with_sama in fields:
        box_bottom = y - field_h
        c.setFont(body, 13)
        c.setFillColor(DARK)
        c.drawString(margin, box_bottom + field_h / 2 - 4, label)

        line_left = margin + label_w
        line_right = PAGE_W - margin - (28 if with_sama else 4)
        c.setStrokeColor(DARK)
        c.setLineWidth(1)
        c.line(line_left, box_bottom + 8, line_right, box_bottom + 8)

        if with_sama:
            c.setFont(body, 14)
            c.setFillColor(DARK)
            c.drawString(line_right + 4, box_bottom + field_h / 2 - 4, "様")

        y = box_bottom - field_gap

    # 下部にも返送の案内を大きく
    c.setFont(body, 14)
    c.setFillColor(RED)
    c.drawCentredString(
        PAGE_W / 2,
        16 * mm,
        "ご記入後、このヒアリングシートを必ずご返送ください",
    )
    c.setFont(body, 10)
    c.setFillColor(GRAY)
    c.drawCentredString(
        PAGE_W / 2,
        10 * mm,
        f"{company.get('company_name', '')}",
    )


# ---------------------------------------------------------------------------
# 宛名ラベル PDF
# ---------------------------------------------------------------------------
# 長形3号封筒（120×235mm）に貼付するラベル枠サイズ
CHOU3_LABEL_W = 95 * mm
CHOU3_LABEL_H = 55 * mm


def generate_labels_pdf(
    customer: dict,
    company: dict,
    *,
    mode: str = "C",
    layout: str = "2面",
    offset_x_mm: float = 0.0,
    offset_y_mm: float = 0.0,
    show_guides: bool = False,
) -> bytes:
    """
    宛名ラベル PDF を生成する。

    mode:
      "C" — 長3封筒貼付用（95×55mm × 往信・返信）
      "A" — A4ノーカット（上下2分割・切り取り線）
      "B" — 市販マルチプリンタラベル（2面 or 4面）
    layout: "2面" | "4面"（mode B のみ）
    """
    ensure_fonts()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    ox = offset_x_mm * mm
    oy = offset_y_mm * mm

    if mode == "C":
        _draw_mode_chou3(c, customer, company, ox, oy, show_guides)
    elif mode == "A":
        _draw_mode_a(c, customer, company, ox, oy, show_guides)
    else:
        _draw_mode_b(c, customer, company, layout, ox, oy, show_guides)

    c.save()
    return buf.getvalue()


def _label_outbound(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    customer: dict,
    show_guides: bool,
    *,
    badge_extra: str = "",
) -> None:
    """往信用ラベル内容を枠内に描画。 (x,y) は左下。"""
    compact = h < 70 * mm
    pad = 4 * mm if compact else 8 * mm
    if show_guides:
        c.setStrokeColor(colors.Color(0.6, 0.6, 0.8))
        c.setDash(1, 2)
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, stroke=1, fill=0)
        c.setDash()

    # 種別バッジ
    badge = "【往信用】お客様宛" + (f"　{badge_extra}" if badge_extra else "")
    c.setFont(_font(True), 7 if compact else 8)
    c.setFillColor(GRAY)
    c.drawString(x + pad, y + h - (5.5 * mm if compact else 8 * mm), badge)

    # 郵便番号
    postal = customer.get("postal_code", "")
    ty = y + h - (11 * mm if compact else 16 * mm)
    if postal:
        c.setFont(_font(True), 12 if compact else 14)
        c.setFillColor(DARK)
        c.drawString(x + pad, ty, f"〒 {postal}")
        ty -= 5.5 * mm if compact else 8 * mm

    # 住所（自動縮小・改行）
    addr = customer.get("address", "")
    addr_max_w = w - 2 * pad
    font_size = 9.5 if compact else 11
    max_addr_lines = 2 if compact else 4
    lines = _wrap_text(addr, _font(), font_size, addr_max_w)
    while len(lines) > max_addr_lines and font_size > 7.0:
        font_size -= 0.5
        lines = _wrap_text(addr, _font(), font_size, addr_max_w)
    for i, line in enumerate(lines[:max_addr_lines]):
        c.setFont(_font(), font_size)
        c.setFillColor(DARK)
        c.drawString(x + pad, ty - i * (font_size + 2), line)
    ty -= len(lines[:max_addr_lines]) * (font_size + 2) + (3.5 * mm if compact else 6 * mm)

    # 氏名＋敬称
    name = customer.get("name", "")
    honorific = customer.get("honorific", "様")
    name_text = f"{name}　{honorific}"
    name_size = _fit_font_size(
        name_text, _font(True), addr_max_w, 14 if compact else 18, 10
    )
    c.setFont(_font(True), name_size)
    c.setFillColor(DARK)
    c.drawString(x + pad, max(ty, y + (10 * mm if compact else 14 * mm)), name_text)

    # 管理番号（左下）
    mgmt = customer.get("management_no", "")
    if mgmt:
        c.setFont(_font(), 7 if compact else 8)
        c.setFillColor(GRAY)
        c.drawString(x + pad, y + (3 * mm if compact else 5 * mm), f"管理番号：{mgmt}")


def _label_return(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    company: dict,
    show_guides: bool,
    *,
    badge_extra: str = "",
) -> None:
    """返信用ラベル内容を枠内に描画。 (x,y) は左下。"""
    compact = h < 70 * mm
    pad = 4 * mm if compact else 8 * mm
    if show_guides:
        c.setStrokeColor(colors.Color(0.6, 0.6, 0.8))
        c.setDash(1, 2)
        c.setLineWidth(0.5)
        c.rect(x, y, w, h, stroke=1, fill=0)
        c.setDash()

    # 種別
    badge = "【返信用】弊社宛" + (f"　{badge_extra}" if badge_extra else "")
    c.setFont(_font(True), 7 if compact else 8)
    c.setFillColor(GRAY)
    c.drawString(x + pad, y + h - (5.5 * mm if compact else 8 * mm), badge)

    # 切手貼付欄（右上）
    stamp_w = 16 * mm if compact else 22 * mm
    stamp_h = 12 * mm if compact else 18 * mm
    sx = x + w - pad - stamp_w
    sy = y + h - (7 * mm if compact else 10 * mm) - stamp_h
    c.setStrokeColor(GRAY)
    c.setDash(2, 2)
    c.setLineWidth(0.8)
    c.rect(sx, sy, stamp_w, stamp_h, stroke=1, fill=0)
    c.setDash()
    c.setFont(_font(), 6 if compact else 7)
    c.setFillColor(GRAY)
    c.drawCentredString(sx + stamp_w / 2, sy + stamp_h / 2 - 2, "切手貼付欄")

    # 郵便番号・住所
    ty = y + h - (12 * mm if compact else 18 * mm)
    postal = company.get("postal_code", "")
    if postal:
        c.setFont(_font(True), 11 if compact else 13)
        c.setFillColor(DARK)
        c.drawString(x + pad, ty, f"〒 {postal}")
        ty -= 5 * mm if compact else 7 * mm

    addr = company.get("address", "")
    addr_max_w = w - 2 * pad - stamp_w - 2 * mm
    font_size = 8.5 if compact else 10
    max_lines = 2 if compact else 3
    lines = _wrap_text(addr, _font(), font_size, addr_max_w)
    while len(lines) > max_lines and font_size > 6.5:
        font_size -= 0.5
        lines = _wrap_text(addr, _font(), font_size, addr_max_w)
    for i, line in enumerate(lines[:max_lines]):
        c.setFont(_font(), font_size)
        c.setFillColor(DARK)
        c.drawString(x + pad, ty - i * (font_size + 2), line)
    ty -= len(lines[:max_lines]) * (font_size + 2) + (3 * mm if compact else 5 * mm)

    # 社名 部署 御中
    company_name = company.get("company_name", "合同会社山林パートナーズ")
    dept = company.get("department", "山林引き取り受付係")
    c.setFont(_font(True), 9 if compact else 10)
    c.setFillColor(DARK)
    line1 = company_name
    line2 = f"{dept}　御中"
    name_y = max(ty, y + (18 * mm if compact else 28 * mm))
    c.drawString(x + pad, name_y, line1)
    c.setFont(_font(True), 10 if compact else 12)
    c.drawString(x + pad, max(name_y - (11 if compact else 14), y + (10 * mm if compact else 18 * mm)), line2)

    # 重要メッセージ（左下・赤枠赤字）
    msg = "【重要】固定資産税書類・確認書在中"
    msg_size = 6.5 if compact else 8
    c.setFont(_font(True), msg_size)
    msg_w = pdfmetrics.stringWidth(msg, _font(True), msg_size) + 6
    msg_h = 10 if compact else 12
    mx = x + pad
    my = y + (2.5 * mm if compact else 5 * mm)
    c.setStrokeColor(RED)
    c.setFillColor(colors.Color(1, 0.95, 0.95))
    c.setLineWidth(1.0)
    c.rect(mx, my, min(msg_w, w - 2 * pad), msg_h, stroke=1, fill=1)
    c.setFillColor(RED)
    c.drawString(mx + 3, my + 2.5, msg)


def _draw_mode_chou3(
    c: canvas.Canvas,
    customer: dict,
    company: dict,
    ox: float,
    oy: float,
    show_guides: bool,
) -> None:
    """
    モードC: 長形3号封筒（120×235mm）貼付用。
    A4中央に 95×55mm の往信・返信ラベルを上下に配置。
    """
    lw, lh = CHOU3_LABEL_W, CHOU3_LABEL_H
    gap = 18 * mm
    total_h = lh * 2 + gap
    left = (PAGE_W - lw) / 2 + ox
    bottom_y = (PAGE_H - total_h) / 2 + oy
    top_y = bottom_y + lh + gap

    # ページ案内
    c.setFont(_font(True), 10)
    c.setFillColor(DARK)
    c.drawCentredString(
        PAGE_W / 2 + ox,
        PAGE_H - 15 * mm + oy,
        "長形3号封筒（120×235mm）貼付用ラベル",
    )
    c.setFont(_font(), 8)
    c.setFillColor(GRAY)
    c.drawCentredString(
        PAGE_W / 2 + ox,
        PAGE_H - 20 * mm + oy,
        "切り取って封筒おもて面に貼付してください（上：往信／下：返信）",
    )

    # 常に実線枠（切り取りガイド）。show_guides 時は点線ガイドも内側に
    for (lx, ly) in ((left, top_y), (left, bottom_y)):
        c.setStrokeColor(DARK)
        c.setLineWidth(0.9)
        c.setDash()
        c.rect(lx, ly, lw, lh, stroke=1, fill=0)

    _label_outbound(
        c, left, top_y, lw, lh, customer, show_guides, badge_extra="長3封筒用"
    )
    _label_return(
        c, left, bottom_y, lw, lh, company, show_guides, badge_extra="長3封筒用"
    )

    # 中間の切り取り案内
    mid = bottom_y + lh + gap / 2
    c.setStrokeColor(GRAY)
    c.setDash(2, 2)
    c.setLineWidth(0.6)
    c.line(left, mid, left + lw, mid)
    c.setDash()
    c.setFont(_font(), 7)
    c.setFillColor(GRAY)
    c.drawCentredString(left + lw / 2, mid + 2, "✂ 切り取り")


def _draw_mode_a(
    c: canvas.Canvas,
    customer: dict,
    company: dict,
    ox: float,
    oy: float,
    show_guides: bool,
) -> None:
    """モードA: A4上下2分割（上：往信、下：返信）＋切り取り線。"""
    half_h = PAGE_H / 2
    # 上段（往信）
    _label_outbound(
        c, 0 + ox, half_h + oy, PAGE_W, half_h, customer, show_guides
    )
    # 下段（返信）
    _label_return(
        c, 0 + ox, 0 + oy, PAGE_W, half_h, company, show_guides
    )

    # 中央切り取り線
    mid_y = half_h + oy
    c.setStrokeColor(GRAY)
    c.setDash(3, 3)
    c.setLineWidth(0.7)
    c.line(10 * mm + ox, mid_y, PAGE_W - 10 * mm + ox, mid_y)
    c.setDash()
    c.setFont(_font(), 7)
    c.setFillColor(GRAY)
    c.drawCentredString(PAGE_W / 2 + ox, mid_y + 2, "✂ ここから切り取ってください（上：往信／下：返信）")

    # 外側ガイド（常に薄い枠を表示して切り取りやすく）
    if show_guides:
        c.setStrokeColor(colors.Color(0.7, 0.7, 0.7))
        c.setLineWidth(0.4)
        c.rect(5 * mm + ox, 5 * mm + oy, PAGE_W - 10 * mm, PAGE_H - 10 * mm)


def _draw_mode_b(
    c: canvas.Canvas,
    customer: dict,
    company: dict,
    layout: str,
    ox: float,
    oy: float,
    show_guides: bool,
) -> None:
    """モードB: A4 2面 or 4面ラベル。"""
    if layout == "4面":
        # 105mm × 148.5mm × 4
        lw, lh = 105 * mm, 148.5 * mm
        positions = [
            (0 + ox, lh + oy),       # 左上 → 往信
            (lw + ox, lh + oy),      # 右上 → 返信
            (0 + ox, 0 + oy),        # 左下 → 往信（予備）
            (lw + ox, 0 + oy),       # 右下 → 返信（予備）
        ]
        _label_outbound(c, *positions[0], lw, lh, customer, show_guides)
        _label_return(c, *positions[1], lw, lh, company, show_guides)
        _label_outbound(c, *positions[2], lw, lh, customer, show_guides)
        _label_return(c, *positions[3], lw, lh, company, show_guides)
    else:
        # A4 2面: 210mm × 148.5mm
        lw, lh = PAGE_W, 148.5 * mm
        _label_outbound(c, 0 + ox, lh + oy, lw, lh, customer, show_guides)
        _label_return(c, 0 + ox, 0 + oy, lw, lh, company, show_guides)

    if show_guides:
        c.setStrokeColor(colors.Color(0.5, 0.5, 0.7))
        c.setLineWidth(0.5)
        c.setDash(1, 1)
        if layout == "4面":
            c.line(105 * mm + ox, 0 + oy, 105 * mm + ox, PAGE_H + oy)
            c.line(0 + ox, 148.5 * mm + oy, PAGE_W + ox, 148.5 * mm + oy)
        else:
            c.line(0 + ox, 148.5 * mm + oy, PAGE_W + ox, 148.5 * mm + oy)
        c.setDash()


# ---------------------------------------------------------------------------
# 一括 PDF（同封書類 + ラベル）
# ---------------------------------------------------------------------------
def generate_combined_pdf(
    customer: dict,
    company: dict,
    *,
    mode: str = "C",
    layout: str = "2面",
    offset_x_mm: float = 0.0,
    offset_y_mm: float = 0.0,
    show_guides: bool = False,
) -> bytes:
    """確認用：同封書類 + 宛名ラベルを1つの PDF にまとめる。"""
    ensure_fonts()
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    _draw_cover_letter_common(c, company)
    c.showPage()
    _draw_hearing_sheet_common(c, company)
    c.showPage()
    ox = offset_x_mm * mm
    oy = offset_y_mm * mm
    if mode == "C":
        _draw_mode_chou3(c, customer, company, ox, oy, show_guides)
    elif mode == "A":
        _draw_mode_a(c, customer, company, ox, oy, show_guides)
    else:
        _draw_mode_b(c, customer, company, layout, ox, oy, show_guides)
    c.save()
    return buf.getvalue()

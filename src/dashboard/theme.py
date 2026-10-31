"""Visual language of the design: small HTML pieces. All text passes through escape."""
from __future__ import annotations

from html import escape

import streamlit as st

CSS = """
<style>
.block-container{padding:1rem 1.6rem 2rem;max-width:1680px}
header[data-testid=stHeader]{background:transparent;height:0;pointer-events:none}
header[data-testid=stHeader] button{pointer-events:auto}
[data-testid=stToolbar],[data-testid=stDecoration],[data-testid=stStatusWidget]{display:none}
.stRadio [role=radiogroup]{gap:0;background:#0C1824;border:1px solid #1E3244;border-radius:6px;width:fit-content;padding:2px;flex-wrap:nowrap}
.stRadio [role=radiogroup] label{margin:0;padding:6px 15px;border-radius:5px;cursor:pointer;white-space:nowrap}
.stRadio [role=radiogroup] label>div>div:not([data-testid=stMarkdownContainer]){display:none}
[data-testid=stSidebarHeader]{padding:.3rem;height:auto;min-height:0}
.stRadio [role=radiogroup] label:has(input:checked){background:#22B8F0}
.stRadio [role=radiogroup] label:has(input:checked) p{color:#07131D;font-weight:600}
[data-testid=stSidebar]{background:#0C1824;border-right:1px solid #1E3244}
[data-testid=stSidebar] [data-testid=stSidebarContent]{padding-top:.4rem}
h1,h2,h3{letter-spacing:-.02em}
[data-testid=stVerticalBlockBorderWrapper]{background:#0F1E2C;border-color:#1E3244!important;border-radius:8px}
[data-testid=stDataFrame]{border:1px solid #1E3244;border-radius:6px}
button[data-baseweb=tab]{font-size:15px;padding:10px 20px}
.brand{display:flex;align-items:baseline;gap:14px;padding:4px 0}
.brand b{font-size:27px;font-weight:700;color:#fff}.brand span{color:#AFC1D2;font-size:15px}
.page-title{font-size:27px;font-weight:700;color:#fff;margin:4px 0 0}
.page-sub{color:#AFC1D2;font-size:15px;margin:0 0 12px}
.badge{display:inline-block;padding:5px 11px;border-radius:5px;font-size:11.5px;font-weight:600;letter-spacing:.5px;border:1px solid #2B4257;color:#AFC1D2;white-space:nowrap}
.badge.amber{border-color:#F2B95D;color:#F2B95D}.badge.cyan{border-color:#22B8F0;color:#7BDDFA}
.target{color:#AFC1D2;font-size:13px;padding-top:36px;white-space:nowrap}.target b{color:#fff;font-size:16px;margin-left:8px}
.pill{display:inline-block;min-width:38px;text-align:center;padding:3px 7px;border-radius:5px;font-size:12px;font-weight:700;color:#07131D}
.pill.VFR{background:#4ADE9A}.pill.MVFR{background:#38A9FF}.pill.IFR{background:#F2555F}.pill.LIFR{background:#B58CFF}
.pill.Unknown{background:#35495C;color:#E7EEF6}
.station{background:#0F1E2C;border:1px solid #1E3244;border-radius:8px;padding:12px 14px;margin-bottom:10px}
.station.active{border-color:#22B8F0;background:#10283A}
.station .head{color:#fff;font-weight:600;font-size:14px}.station .head span{font-weight:400;color:#AFC1D2;font-size:13px}
.station .now{display:flex;gap:12px;align-items:center;margin:9px 0 6px;color:#fff;font-size:18px;font-weight:600}
.station .line{color:#C9D6E2;font-size:13px;line-height:1.55}
.station .label{color:#8FA5B8;font-size:11.5px;margin:8px 0 5px;border-top:1px solid #1E3244;padding-top:7px}
.chips{display:flex;gap:5px;color:#AFC1D2;font-size:11px;align-items:center}
.source-row{display:flex;gap:9px;align-items:center;color:#C9D6E2;font-size:12.5px;padding:2.5px 0}
.dot{width:9px;height:9px;border-radius:50%;flex:none}.dot.available{background:#4ADE9A}.dot.partial{background:#F2B95D}.dot.unavailable{background:#F2555F}
.tile{background:#0F1E2C;border:1px solid #1E3244;border-radius:8px;padding:13px 16px;min-height:112px;margin-bottom:12px}
.tile .label{color:#C9D6E2;font-size:13.5px}.tile .value{color:#fff;font-size:31px;font-weight:700;line-height:1.25}
.tile .value.warn{color:#F2B95D}.tile .value.alert{color:#F2555F}
.tile .note{color:#8FA5B8;font-size:11.5px}
.card-title{color:#fff;font-size:16px;font-weight:600;margin:0 0 7px}
.card-note{color:#8FA5B8;font-size:12px;margin:0 0 7px}
.banner{border:1px solid #F2B95D;background:#2A2413;color:#F2CF8E;border-radius:6px;padding:9px 13px;font-size:13.5px;margin:0 0 10px}
.banner.quiet{border-color:#2B4257;background:#0C1824;color:#AFC1D2}
.grid{width:100%;border-collapse:collapse;font-size:13px;color:#DCE6F1}
.grid th,.grid td{border:0!important}
.grid th{color:#AFC1D2;font-weight:500;text-align:left;padding:7px 10px;border-bottom:1px solid #2B4257!important}
.grid td{padding:7px 10px;border-bottom:1px solid #1E3244!important}
.grid th.on,.grid td.on{background:#123045}
.steps{display:flex;gap:6px;margin:0 0 6px}
.step{flex:1;background:#13283A;text-align:center;padding:9px;color:#fff;font-weight:600;font-size:14px;clip-path:polygon(0 0,calc(100% - 14px) 0,100% 50%,calc(100% - 14px) 100%,0 100%,12px 50%)}
.step span{display:block;font-weight:400;color:#AFC1D2;font-size:12px}
.check{display:flex;justify-content:space-between;gap:12px;color:#DCE6F1;font-size:13px;padding:6px 0;border-bottom:1px solid #1E3244}
.check b{font-weight:500;white-space:nowrap}.check b.pass{color:#4ADE9A}.check b.fail{color:#F2555F}.check b.none{color:#F2B95D}
.heat{width:100%;border-collapse:separate;border-spacing:3px;font-size:13.5px;color:#fff}
.heat th{color:#AFC1D2;font-weight:500;padding:6px 8px;text-align:center;border:0!important}
.heat th:first-child,.heat td:first-child{text-align:left;color:#DCE6F1;background:none;font-weight:500}
.heat td{padding:10px 8px;text-align:center;font-weight:600;border:0!important;border-radius:3px}
.heat th.on{color:#7BDDFA}.heat td.on{outline:2px solid #22B8F0;outline-offset:-1px}
.scale{height:9px;border-radius:5px;background:linear-gradient(90deg,#1B2B2A,#6E6A2A,#E8A33D,#E0603C,#D01F4F);margin-top:10px}
.scale-labels{display:flex;justify-content:space-between;color:#8FA5B8;font-size:11px;margin-top:3px}
.bar-row{display:flex;align-items:center;gap:10px;font-size:13px;color:#DCE6F1;padding:3px 0}
.bar-row .name{width:122px}.bar-row .bar{flex:1;height:8px;background:#1E3244;border-radius:4px;overflow:hidden}
.bar-row .fill{height:100%;background:#F2B95D}.bar-row .fill.high{background:#F2555F}.bar-row .pct{width:42px;text-align:right}
.split{display:flex;gap:18px}.split>div{flex:1}.split .big{font-size:29px;font-weight:700;color:#fff;line-height:1.2}.split .big small{font-size:14px;color:#AFC1D2}
.split .cap{color:#AFC1D2;font-size:12px}
.flight{display:flex;justify-content:space-between;gap:8px;font-size:12.5px;color:#DCE6F1;padding:5px 0;border-bottom:1px solid #1E3244}
.flight b{color:#F2B95D}.flight span.dim{color:#8FA5B8}
.footnote{color:#6F8598;font-size:11.5px;text-align:right;margin-top:10px}
</style>
"""


def html(markup: str, target=st) -> None:
    target.markdown(markup, unsafe_allow_html=True)


def pill(category: str) -> str:
    return f'<span class="pill {escape(category)}">{escape(category)}</span>'


def tile(label: str, value, note: str = "", tone: str = "") -> str:
    return (
        f'<div class="tile"><div class="label">{escape(label)}</div>'
        f'<div class="value {tone}">{escape(str(value))}</div><div class="note">{escape(note)}</div></div>'
    )


def title(text: str, subtitle: str = "") -> None:
    html(f'<div class="page-title">{escape(text)}</div><div class="page-sub">{escape(subtitle)}</div>')


def card_title(text: str, note: str = "") -> None:
    html(f'<div class="card-title">{escape(text)}</div>' + (f'<div class="card-note">{escape(note)}</div>' if note else ""))


def heat_color(share: float) -> str:
    """Scale is capped at 40%: these conditions are rare, so the full 100% range would look flat."""
    stops = [(27, 43, 42), (110, 106, 42), (232, 163, 61), (224, 96, 60), (208, 31, 79)]
    position = min(share / 0.4, 1) * (len(stops) - 1)
    low = min(int(position), len(stops) - 2)
    mix = position - low
    rgb = [round(a + (b - a) * mix) for a, b in zip(stops[low], stops[low + 1])]
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def heatmap(columns: list[str], values: dict[str, list[float | None]], highlight: int | None) -> str:
    def cls(index):
        return ' class="on"' if index == highlight else ""

    head = "<th></th>" + "".join(f"<th{cls(i)}>{escape(c)}</th>" for i, c in enumerate(columns))
    rows = ""
    for label, shares in values.items():
        cells = "".join(
            f'<td{cls(i)} style="background:{"#1E3244" if s is None else heat_color(s)}">{"n/a" if s is None else f"{s:.0%}"}</td>'
            for i, s in enumerate(shares)
        )
        rows += f"<tr><td>{escape(label)}</td>{cells}</tr>"
    return (
        f'<table class="heat"><tr>{head}</tr>{rows}</table><div class="scale"></div>'
        '<div class="scale-labels"><span>0%</span><span>10%</span><span>20%</span><span>30%</span><span>40%+</span></div>'
    )


def bars(values: dict[str, float | None]) -> str:
    rows = ""
    for label, share in values.items():
        width = 0 if share is None else min(share / 0.4, 1) * 100
        shown = "n/a" if share is None else f"{share:.0%}"
        tone = " high" if share is not None and share >= 0.2 else ""
        rows += (
            f'<div class="bar-row"><span class="name">{escape(label)}</span><span class="bar">'
            f'<div class="fill{tone}" style="width:{width:.0f}%"></div></span><span class="pct">{shown}</span></div>'
        )
    return rows


def grid(headers: list[str], rows: list[list[str]], highlight: int | None = None) -> str:
    """Cells are trusted markup, so callers escape values or pass pill()."""

    def cls(index):
        return ' class="on"' if index == highlight else ""

    head = "".join(f"<th{cls(i)}>{escape(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td{cls(i)}>{cell}</td>" for i, cell in enumerate(row)) + "</tr>" for row in rows
    )
    return f'<table class="grid"><tr>{head}</tr>{body}</table>'

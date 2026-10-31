"""Design tokens and HTML primitives, mirroring the Figma library. All text passes through escape.

TOKENS use the same names as the Figma variables' code syntax. Styling hooks are our own classes
and the documented `st-key-*` class from `st.container(key=...)`. The only undocumented selectors
sit in UNSTABLE_CSS, and losing them costs spacing, not function.
"""
from __future__ import annotations

from html import escape

import streamlit as st

TOKENS = {
    "bg-app": "#14181B", "bg-card": "#1B2023", "bg-inset": "#20272B", "border": "#364149",
    "text-primary": "#EDF1F4", "text-secondary": "#ADBAC5", "text-on-accent": "#10171B",
    "cyan": "#00D4F5", "amber": "#FFCD38", "red": "#FF4B4B", "green": "#69DF82", "violet": "#8BBBD6",
    "cat-vfr": "#69DF82", "cat-mvfr": "#40BAF5", "cat-ifr": "#FF4B4B", "cat-lifr": "#C78ADA",
    "space-xs": "4px", "space-sm": "8px", "space-md": "12px", "space-lg": "16px", "space-xl": "24px",
    "radius-sm": "4px", "radius-md": "6px",
}

ICONS = {
    "plane": '<path d="M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"/>',
    "cloud": '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
    "storm": '<path d="M6 16.326A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973"/><path d="m13 12-3 5h4l-3 5"/>',
    "eye": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "eyeoff": '<path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><path d="m2 2 20 20"/>',
    "wind": '<path d="M17.7 7.7a2.5 2.5 0 1 1 1.8 4.3H2"/><path d="M9.6 4.6A2 2 0 1 1 11 8H2"/><path d="M12.6 19.4A2 2 0 1 0 14 16H2"/>',
    "thermo": '<path d="M14 4v10.54a4 4 0 1 1-4 0V4a2 2 0 0 1 4 0Z"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "cross": '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "warn": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
    "file": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "bars": '<path d="M12 20V10"/><path d="M18 20V4"/><path d="M6 20v-4"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "trend": '<path d="M22 7 13.5 15.5l-5-5L2 17"/><path d="M16 7h6v6"/>',
    "table": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/>',
    "clipboard": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
    "landing": '<path d="M2 22h20"/><path d="M3.77 10.77 2 9l2-4.5 1.12.55c.55.28.9.84.9 1.45s.35 1.17.9 1.45L8 8.5l3-6 1.05.53a2 2 0 0 1 1.09 1.52l.72 5.4a2 2 0 0 0 1.09 1.52l4.4 2.2c.42.22.78.55 1.01.96l.6 1.03c.49.88-.06 1.98-1.06 2.1l-1.18.15c-.47.06-.95-.02-1.37-.24L4.29 11.15a2 2 0 0 1-.52-.38Z"/>',
    "takeoff": '<path d="M2 22h20"/><path d="M6.36 17.4 4 17l-2-4 1.1-.55a2 2 0 0 1 1.8 0l.17.1a2 2 0 0 0 1.8 0L8 12 5 6l.9-.45a2 2 0 0 1 2.09.2l4.02 3a2 2 0 0 0 2.1.2l4.19-2.06a2.41 2.41 0 0 1 1.73-.17L21 7a1.4 1.4 0 0 1 .87 1.99l-.38.76c-.23.46-.6.84-1.07 1.08L7.58 17.2a2 2 0 0 1-1.22.18Z"/>',
    "swap": '<path d="m16 3 4 4-4 4"/><path d="M20 7H4"/><path d="m8 21-4-4 4-4"/><path d="M4 17h16"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4"/><path d="M8 2v4"/><path d="M3 10h18"/>',
}

_ROOT = ":root{" + "".join(f"--{name}:{value};" for name, value in TOKENS.items()) + "}"

CSS = _ROOT + """
.st-key-app-header,.st-key-toolbar{border-bottom:1px solid var(--border);padding:8px 16px;align-items:center}
.st-key-rail{border-right:1px solid var(--border);padding:12px 16px 12px 16px}
.st-key-main{padding:16px 28px 28px;min-width:0}
[class*="st-key-card-"]{background:var(--bg-card);padding:20px 24px;margin-bottom:8px}
[class*="st-key-tile-"]{background:var(--bg-card)}
.brand{display:flex;align-items:center;gap:12px}
.brand svg{width:30px;height:30px;stroke:var(--cyan)}
.brand b{font-size:24px;line-height:30px;font-weight:700;color:var(--text-primary);white-space:nowrap}
.brand span{color:var(--text-secondary);font-size:14px}
.tb-target{color:var(--text-secondary);font-size:12px;white-space:nowrap}
.tb-target b{color:var(--text-primary);font-size:14px;font-weight:500;margin-left:8px}
.page-title{font-size:28px;line-height:34px;font-weight:700;color:var(--text-primary);margin:0}
.page-sub{color:var(--text-secondary);font-size:14px;line-height:20px;margin:4px 0 0}
.card-title{display:flex;align-items:center;gap:8px;color:var(--text-primary);font-size:16px;line-height:22px;font-weight:600}
.card-title svg{width:18px;height:18px;flex:none}
.card-note{color:var(--text-secondary);font-size:12px;line-height:16px;margin-top:4px}
.ico{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;stroke:currentColor}
.badge{display:inline-block;padding:3px 8px;border-radius:var(--radius-sm);border:1px solid var(--text-secondary);color:var(--text-secondary);font-size:11px;line-height:14px;font-weight:500;white-space:nowrap;letter-spacing:.02em}
.badge.amber{border-color:var(--amber);color:var(--amber)}.badge.cyan{border-color:var(--cyan);color:var(--cyan)}
.badge.green{border-color:var(--green);color:var(--green)}.badge.red{border-color:var(--red);color:var(--red)}.badge.violet{border-color:var(--violet);color:var(--violet)}
.chip{display:inline-block;min-width:34px;text-align:center;padding:3px 8px;border-radius:var(--radius-sm);font-size:11px;line-height:14px;font-weight:600;color:var(--text-on-accent)}
.chip.VFR{background:var(--cat-vfr)}.chip.MVFR{background:var(--cat-mvfr)}.chip.IFR{background:var(--cat-ifr)}.chip.LIFR{background:var(--cat-lifr)}.chip.Unknown{background:var(--bg-inset);color:var(--text-secondary);border:1px solid var(--border)}
.side-title{color:var(--text-primary);font-size:16px;line-height:22px;font-weight:600;margin:0 0 4px}
.side-line{color:var(--text-secondary);font-size:12px;line-height:18px}
.side-line.cyan{color:var(--cyan)}
.status-row{display:flex;gap:8px;align-items:center;font-size:12px;line-height:24px;color:var(--text-secondary)}
.status-row span{flex:1;min-width:0}.status-row b{font-weight:400;color:var(--text-primary);white-space:nowrap}
.dot{width:8px;height:8px;border-radius:50%;flex:none;background:var(--text-secondary)}
.dot.available,.dot.green{background:var(--green)}.dot.partial,.dot.amber{background:var(--amber)}.dot.unavailable,.dot.red{background:var(--red)}
.tile{display:flex;gap:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:20px;min-height:128px;height:100%;box-sizing:border-box}
.tile>svg{width:24px;height:24px;flex:none;color:var(--cyan)}
.tile .body{min-width:0;flex:1}
.tile .label{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;color:var(--text-secondary);font-size:14px;line-height:22px;font-weight:500}
.tile .value{color:var(--text-primary);font-size:26px;line-height:32px;font-weight:700;margin:4px 0;font-variant-numeric:tabular-nums}
.tile .note{color:var(--text-secondary);font-size:12px;line-height:19px;margin-top:8px}
.tile.cyan .value,.tile.cyan>svg{color:var(--cyan)}.tile.violet .value,.tile.violet>svg{color:var(--violet)}.tile.red .value,.tile.red>svg{color:var(--red)}.tile.amber .value,.tile.amber>svg{color:var(--amber)}.tile.green .value,.tile.green>svg{color:var(--green)}
.tile.muted .value{color:var(--text-secondary)}
.strip{display:flex;align-items:center;gap:12px;background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-md);padding:8px 16px;font-size:14px;line-height:20px;color:var(--text-secondary);flex-wrap:wrap}
.strip svg{width:18px;height:18px;flex:none;color:var(--cyan)}.strip b{color:var(--text-primary);font-weight:500}
.notice{display:flex;gap:8px;align-items:flex-start;border:1px solid var(--amber);background:rgba(244,188,73,.08);color:var(--amber);border-radius:var(--radius-md);padding:8px 12px;font-size:13px;line-height:18px}
.notice svg{width:18px;height:18px;flex:none;margin-top:1px}.notice.quiet{border-color:var(--border);background:var(--bg-inset);color:var(--text-secondary)}
.notice.red{border-color:var(--red);background:rgba(242,107,115,.08);color:var(--red)}
.notice b{font-weight:600}
.table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius-md)}
.grid{width:100%;border-collapse:collapse;font-size:13px;line-height:18px;color:var(--text-primary);font-variant-numeric:tabular-nums}
.grid th,.grid td{border:0!important;padding:8px 12px;text-align:left;white-space:nowrap}
.grid td.wrap{white-space:normal;min-width:240px}
.grid th{background:var(--bg-inset);color:var(--text-secondary);font-weight:500}
.grid tr+tr td,.grid tr td{border-top:1px solid var(--border)!important}
.grid tr.on td{background:var(--bg-inset);color:var(--cyan)}
.grid th.in{color:var(--cyan)}.grid th.out{color:var(--violet)}
.grid td.green{color:var(--green)}.grid td.red{color:var(--red)}.grid td.amber{color:var(--amber)}.grid td.dim,.grid td.secondary{color:var(--text-secondary)}
.heat{width:100%;border-collapse:separate;border-spacing:4px;font-size:13px;color:var(--text-primary)}
.heat th{color:var(--text-secondary);font-weight:500;padding:4px 8px;text-align:center;border:1px solid transparent!important;font-size:12px;line-height:16px;border-radius:var(--radius-sm)}
.heat th small{display:block;font-size:11px}
.heat th:first-child{text-align:left}.heat td:first-child{text-align:left;background:none!important;color:var(--text-primary);padding-left:0;white-space:nowrap}
.heat td{padding:8px;text-align:center;font-weight:500;border:0!important;border-radius:var(--radius-sm);font-variant-numeric:tabular-nums}
.heat th.on{color:var(--cyan);border-color:var(--cyan)!important}.heat td.on{outline:1px solid var(--cyan);outline-offset:-1px}
.bar-row{display:flex;align-items:center;gap:8px;font-size:12px;line-height:20px;color:var(--text-secondary)}
.bar-row .name{width:112px;flex:none}.bar-row .bar{flex:1;height:8px;background:var(--bg-inset);border-radius:var(--radius-sm);overflow:hidden}
.bar-row .fill{height:100%;background:var(--amber)}.bar-row .fill.high{background:var(--red)}
.bar-row .pct{width:36px;text-align:right;color:var(--text-primary);font-variant-numeric:tabular-nums}
.split{display:flex;gap:16px}.split>div{flex:1;min-width:0}
.split .cap{color:var(--text-secondary);font-size:12px;line-height:16px}
.split .big{font-size:26px;line-height:32px;font-weight:700;color:var(--text-primary);margin-top:4px;font-variant-numeric:tabular-nums}.split .big small{font-size:14px;font-weight:500;color:var(--text-secondary)}
.split .big.none{color:var(--text-secondary)}
.flight{display:flex;justify-content:space-between;gap:8px;font-size:12px;line-height:20px;color:var(--text-primary)}
.flight b{color:var(--amber);font-weight:600}.flight span.dim{color:var(--text-secondary)}
.log{display:flex;flex-direction:column;gap:12px;margin:0;padding:0}
.log div{display:flex;gap:12px;align-items:center;color:var(--text-primary);font-size:14px;line-height:20px}
.log i{width:10px;height:10px;border:2px solid var(--cyan);border-radius:50%;flex:none}.log b{font-weight:600;font-variant-numeric:tabular-nums}
.totals{display:flex;background:var(--bg-inset);border-radius:var(--radius-sm);padding:8px 12px;gap:12px}
.totals div{flex:1;text-align:center;color:var(--text-secondary);font-size:11px;line-height:14px}
.totals b{display:block;margin-top:2px;color:var(--text-primary);font-size:15px;line-height:20px;font-weight:600;font-variant-numeric:tabular-nums}.totals b.red{color:var(--red)}.totals b.none{color:var(--text-secondary)}
.empty{display:flex;flex-direction:column;align-items:center;gap:4px;background:var(--bg-inset);border-radius:var(--radius-md);padding:24px 12px;text-align:center;color:var(--text-secondary);font-size:12px;line-height:16px}
.empty svg{width:28px;height:28px}.empty b{color:var(--text-primary);font-size:14px;font-weight:500}
.steps{display:flex;gap:8px}
.step{flex:1;background:var(--bg-inset);border:1px solid var(--border);border-radius:var(--radius-sm);text-align:center;padding:4px 12px;color:var(--text-primary);font-weight:500;font-size:14px;line-height:20px}
.step span{display:block;font-weight:500;color:var(--text-secondary);font-size:11px;line-height:14px}
.check{display:flex;justify-content:space-between;gap:12px;color:var(--text-primary);font-size:13px;line-height:28px}
.check b{font-weight:500;white-space:nowrap}.check b.pass{color:var(--green)}.check b.fail{color:var(--red)}.check b.none{color:var(--amber)}
.conditions{display:flex;gap:24px;align-items:center;flex-wrap:wrap}
.conditions>svg{width:44px;height:44px;color:var(--text-primary)}
.conditions .item{flex:1;min-width:120px;display:flex;gap:8px;align-items:center;color:var(--text-secondary);font-size:12px;line-height:16px}
.conditions .item svg{width:20px;height:20px;flex:none}.conditions .item b{display:block;color:var(--text-primary);font-size:15px;line-height:20px;font-weight:600}
.cat-col{display:flex;flex-direction:column;align-items:center;gap:4px;color:var(--text-secondary);font-size:11px}
.footnote{color:var(--text-secondary);font-size:11px;line-height:14px;text-align:right}
.brand-row,.head-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.st-key-scenario-baseline{border:1px solid #A3AFB8!important;background:linear-gradient(145deg,#252B30,#191E22)}
.st-key-scenario-hold{border:1px solid var(--amber)!important;background:linear-gradient(145deg,#302A1B,#1B2023)}
.st-key-scenario-reroute{border:1px solid var(--cyan)!important;background:linear-gradient(145deg,#183039,#1B2023)}
.st-key-scenario-hold strong{color:var(--amber)}
.st-key-scenario-reroute strong{color:var(--cyan)}
.st-key-app-header,.st-key-toolbar{background:linear-gradient(180deg,#22282D,#171C20)}
[class*="st-key-card-"],.tile{box-shadow:inset 0 1px 0 rgba(255,255,255,.035)}
.st-key-card-flight-watchlist{border-left:3px solid var(--cyan)!important;background:linear-gradient(110deg,#183039,#1B2023)}
.st-key-card-response,.st-key-card-scenarios{border-left:3px solid var(--amber)!important;background:linear-gradient(110deg,#302A1B,#1B2023)}
.st-key-card-coverage,.st-key-card-integrity{border-left:3px solid #8BBBD6!important;background:linear-gradient(110deg,#222C34,#1B2023)}
.flight-risk-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;padding:2px 6px 4px 0;max-height:200px;overflow-y:auto}
.flight-risk-card{--risk:#ADBAC5;background:#1B2023;border:1px solid #364149;border-left:4px solid var(--risk);border-radius:6px;padding:10px 12px;color:#EDF1F4}
.flight-risk-card.red{--risk:#FF4B4B;background:linear-gradient(115deg,#352226,#1B2023)}
.flight-risk-card.amber{--risk:#FFCD38;background:linear-gradient(115deg,#322E20,#1B2023)}
.flight-risk-card.cyan{--risk:#00D4F5;background:linear-gradient(115deg,#1B2B32,#1B2023)}
.flight-risk-head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:14px}
.flight-risk-head span,.flight-risk-meta{color:#ADBAC5;font-size:12px}
.flight-risk-score{display:flex;align-items:center;gap:12px;margin:14px 0 10px}
.flight-risk-score strong{font-size:26px;color:var(--risk);font-variant-numeric:tabular-nums}
.flight-risk-score span{font-size:12px;color:#ADBAC5}
.flight-risk-status{font-size:12px;color:var(--risk);margin-bottom:8px}
"""

# Undocumented Streamlit structure. Each rule is cosmetic, so a rename only loosens the layout.
UNSTABLE_CSS = """
.stMainBlockContainer,.block-container{padding:0!important;max-width:none!important}
[data-testid=stHeader]{display:none}
.st-key-main [data-testid=stHorizontalBlock]{gap:24px}
.st-key-main [data-testid=stVerticalBlock]{row-gap:18px}
.st-key-main [data-testid=stVerticalBlockBorderWrapper]{padding:6px}
.st-key-main [data-baseweb=tab-panel]{padding-top:20px}
@media(max-width:900px){.st-key-main{padding:12px 14px 20px}.st-key-main [data-testid=stHorizontalBlock]{gap:12px}[class*="st-key-card-"]{padding:16px}.tile{padding:16px}}
"""


def inject() -> None:
    st.html(f"<style>{CSS}{UNSTABLE_CSS}</style>")


def html(markup: str, target=st) -> None:
    target.markdown(markup, unsafe_allow_html=True)


def icon(name: str) -> str:
    return f'<svg class="ico" viewBox="0 0 24 24" aria-hidden="true">{ICONS[name]}</svg>'


def chip(category: str) -> str:
    return f'<span class="chip {escape(category)}">{escape(category)}</span>'


def badge(label: str, tone: str = "") -> str:
    return f'<span class="badge {tone}">{escape(label)}</span>'


def tile(label: str, value, note: str = "", tone: str = "", glyph: str | None = None, tag: str = "") -> str:
    """Figma KPI Card. `tag` is trusted markup, normally a badge()."""
    mark = icon(glyph) if glyph else ""
    return (
        f'<div class="tile {tone}">{mark}<div class="body"><div class="label"><span>{escape(label)}</span>{tag}</div>'
        f'<div class="value">{escape(str(value))}</div><div class="note">{escape(note)}</div></div></div>'
    )


def title(text: str, subtitle: str = "", target=st) -> None:
    html(f'<div class="page-title">{escape(text)}</div><div class="page-sub">{escape(subtitle)}</div>', target)


def card(key: str, **options):
    return st.container(border=True, key=f"card-{key}", **options)


def card_title(text: str, note: str = "", glyph: str | None = None, target=st) -> None:
    mark = f'<span style="color:var(--cyan);display:flex">{icon(glyph)}</span>' if glyph else ""
    extra = f'<div class="card-note">{escape(note)}</div>' if note else ""
    html(f'<div class="card-title">{mark}{escape(text)}</div>{extra}', target)


def strip(glyph: str, label: str, detail: str, target=st) -> None:
    html(f'<div class="strip">{icon(glyph)}<b>{escape(label)}</b><span>{escape(detail)}</span></div>', target)


def notice(text: str, tone: str = "", glyph: str = "alert", target=st) -> None:
    html(f'<div class="notice {tone}">{icon(glyph)}<div>{text}</div></div>', target)


def status_row(tone: str, name: str, value: str) -> str:
    return (
        f'<div class="status-row" title="{escape(name)}: {escape(value)}"><i class="dot {tone}"></i>'
        f'<span>{escape(name)}</span><b>{escape(value)}</b></div>'
    )


def empty(glyph: str, heading: str, detail: str) -> str:
    return f'<div class="empty">{icon(glyph)}<b>{escape(heading)}</b>{escape(detail)}</div>'


def heat_color(share: float) -> str:
    """Sequential amber scale, capped at 60% so rare conditions still separate."""
    return f"rgba(244,188,73,{0.08 + min(share / 0.6, 1) * 0.62:.2f})"


def heatmap(columns: list[tuple[str, str]], values: dict[str, list[float | None]], highlight: int | None) -> str:
    def cls(index):
        return ' class="on"' if index == highlight else ""

    head = "<th>Condition</th>" + "".join(
        f"<th{cls(i)}>{escape(a)}<small>{escape(b)}</small></th>" for i, (a, b) in enumerate(columns)
    )
    rows = ""
    for label, shares in values.items():
        cells = "".join(
            f'<td{cls(i)} style="background:{"var(--bg-inset)" if s is None else heat_color(s)}">{"n/a" if s is None else f"{s:.0%}"}</td>'
            for i, s in enumerate(shares)
        )
        rows += f"<tr><td>{escape(label)}</td>{cells}</tr>"
    return f'<table class="heat"><tr>{head}</tr>{rows}</table>'


def bars(values: dict[str, float | None]) -> str:
    rows = ""
    for label, share in values.items():
        width = 0 if share is None else min(share, 1) * 100
        shown = "n/a" if share is None else f"{share:.0%}"
        tone = " high" if share is not None and share >= 0.5 else ""
        rows += (
            f'<div class="bar-row"><span class="name">{escape(label)}</span><span class="bar">'
            f'<div class="fill{tone}" style="width:{width:.0f}%"></div></span><span class="pct">{shown}</span></div>'
        )
    return rows


def table(headers: list[str], rows: list[list[str]], selected: int | None = None, head_classes: dict[int, str] | None = None, cell_classes: dict[tuple[int, int], str] | None = None) -> str:
    """Figma Table Row, horizontally scrollable. Cells are trusted, so callers escape values."""
    head_classes, cell_classes = head_classes or {}, cell_classes or {}
    head = "".join(f'<th class="{head_classes.get(i, "")}">{escape(h)}</th>' for i, h in enumerate(headers))
    body = "".join(
        f'<tr class="{"on" if r == selected else ""}">'
        + "".join(f'<td class="{cell_classes.get((r, c), "")}">{cell}</td>' for c, cell in enumerate(row))
        + "</tr>"
        for r, row in enumerate(rows)
    )
    return f'<div class="table-wrap"><table class="grid"><tr>{head}</tr>{body}</table></div>'

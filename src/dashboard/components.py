"""Custom Components v2: interactions that native widgets cannot express.

The map keeps layer toggles in the browser and sends airport and horizon changes to Python. The
watchlist sends the clicked airport. Both are registered in the active runtime on each render. All text reaches the
browser through textContent, so no value is interpreted as markup.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

STATIC = Path(__file__).resolve().parent / "static"

WATCHLIST_CSS = """
.rail{display:flex;flex-direction:column;gap:12px;font-family:Inter,system-ui,sans-serif}
.card{display:flex;flex-direction:column;gap:8px;width:100%;box-sizing:border-box;text-align:left;font:inherit;color:#F1F5F9;background:#141C25;border:1px solid #2A3947;border-radius:6px;padding:12px;cursor:pointer}
.card[aria-pressed=true]{background:#19232E;border-color:#28C6F4}
.card:focus-visible{outline:2px solid #28C6F4;outline-offset:2px}
.title{font-size:14px;line-height:20px;font-weight:500}
.now{display:flex;gap:12px;align-items:center}
.now svg{width:36px;height:36px;flex:none;fill:none;stroke:#F1F5F9;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.line{display:flex;gap:12px;align-items:center;font-size:15px;line-height:20px;font-weight:600}
.small{color:#93A4B5;font-size:12px;line-height:16px;margin-top:3px}
.chip{display:inline-block;min-width:30px;text-align:center;padding:3px 7px;border-radius:4px;font-size:11px;line-height:14px;font-weight:600;color:#0C1117;background:#2A3947}
.chip.VFR{background:#62C995}.chip.MVFR{background:#3B9BFF}.chip.IFR{background:#F26B73}.chip.LIFR{background:#A97BF5}.chip.Unknown{color:#93A4B5;background:#19232E;box-shadow:inset 0 0 0 1px #2A3947}
hr{width:100%;border:0;border-top:1px solid #2A3947;margin:0}
.leads{display:flex;gap:4px;align-items:center;color:#93A4B5;font-size:11px;line-height:14px;font-weight:500}
.status{display:flex;gap:8px;align-items:center;font-size:12px;line-height:16px}
.status i{width:8px;height:8px;border-radius:50%}
.status.available{color:#62C995}.status.available i{background:#62C995}.status.cached{color:#F4BC49}.status.cached i{background:#F4BC49}.status.unavailable{color:#F26B73}.status.unavailable i{background:#F26B73}
"""

WATCHLIST_JS = """
const GLYPHS = {
  storm: '<path d="M6 16.326A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 .5 8.973"/><path d="m13 12-3 5h4l-3 5"/>',
  cloud: '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/>',
  sun: '<path d="M12 2v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="M20 12h2"/><path d="m19.07 4.93-1.41 1.41"/><path d="M15.947 12.65a4 4 0 0 0-5.925-4.128"/><path d="M13 22H7a5 5 0 1 1 4.9-6H13a3 3 0 0 1 0 6Z"/>',
};
function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = text;
  return item;
}
function chip(category) { return node('span', `chip ${category}`, category); }
function card(entry, setTriggerValue) {
  const button = node('button', 'card');
  button.type = 'button';
  button.setAttribute('aria-pressed', String(entry.active));
  button.setAttribute('aria-label', `Select ${entry.title}`);
  button.onclick = () => setTriggerValue('select', entry.icao);
  button.append(node('div', 'title', entry.title));
  if (entry.source) button.append(node('div', 'small', entry.source));
  if (entry.status) {
    const status = node('div', `status ${entry.status}`);
    status.append(node('i'), entry.statusLabel);
    button.append(status);
  }
  if (entry.empty) { button.append(node('div', 'small', entry.empty)); return button; }
  const now = node('div', 'now');
  now.insertAdjacentHTML('beforeend', `<svg viewBox="0 0 24 24" aria-hidden="true">${GLYPHS[entry.glyph] || GLYPHS.cloud}</svg>`);
  const readout = node('div');
  const line = node('div', 'line');
  line.append(chip(entry.category), entry.temperature);
  readout.append(line);
  entry.details.forEach(text => readout.append(node('div', 'small', text)));
  now.append(readout);
  button.append(now);
  if (entry.leads && entry.leads.length) {
    button.append(node('hr'), node('div', 'small', 'Forecast (vs. cutoff)'));
    const leads = node('div', 'leads');
    entry.leads.forEach(lead => leads.append(`+${lead.lead}h`, chip(lead.category)));
    button.append(leads);
  }
  return button;
}
export default function ({data, parentElement, setTriggerValue}) {
  const root = parentElement.querySelector('.rail');
  root.replaceChildren(...data.cards.map(entry => card(entry, setTriggerValue)));
}
"""


def _map_component():
    library = (STATIC / "leaflet.js").read_text(encoding="utf-8")
    script = (STATIC / "ops_map.js").read_text(encoding="utf-8")
    style = (STATIC / "leaflet.css").read_text(encoding="utf-8") + (STATIC / "ops_map.css").read_text(encoding="utf-8")
    return st.components.v2.component(
        "ops_map", html='<div class="ops-root"></div>', css=style, js=f"{library}\n{script}",
    )


def _watchlist_component():
    return st.components.v2.component("watchlist", html='<div class="rail"></div>', css=WATCHLIST_CSS, js=WATCHLIST_JS)


def ops_map(payload: dict, key: str, on_airport_change=None, on_horizon_change=None):
    def ignore():
        pass

    return _map_component()(
        data=payload, key=key, on_airport_change=on_airport_change or ignore,
        on_horizon_change=on_horizon_change or ignore,
    )


def watchlist(cards: list[dict], key: str, on_select_change):
    return _watchlist_component()(data={"cards": cards}, key=key, on_select_change=on_select_change)

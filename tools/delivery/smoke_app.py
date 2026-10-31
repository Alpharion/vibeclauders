"""Functional app smoke; browser-side map tiles are outside this check."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path, help="Write machine-readable results for release verification")
    args = parser.parse_args()
    def finish(checks):
        failed = any(c["exceptions"] for c in checks)
        result = {"status": "failed" if failed else "passed", "checks": checks}
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return int(failed)
    os.environ["DASHBOARD_DATA_ROOT"] = str(args.root.resolve())
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(args.root / "app.py"), default_timeout=60).run()
    checks = [{"case": "initial", "exceptions": [x.message for x in app.exception]}]
    if not app.exception:
        for airport in ("KATL", "KDFW"):
            for lead in (3, 6, 12):
                for reveal in (False, True):
                    app.selectbox(key="airport").set_value(airport)
                    next(w for w in app.get("button_group") if w.key == "horizon").set_value(lead)
                    app.session_state["reveal"] = reveal
                    app.run()
                    errors = [x.message for x in app.exception]
                    visited = []
                    for tab in ("Overview", "Weather", "Traffic", "Compare", "Evaluation"):
                        if errors:
                            break
                        app.session_state["tab"] = tab
                        app.session_state["reveal"] = reveal
                        app.run()
                        visited.append(tab)
                        errors.extend(x.message for x in app.exception)
                    checks.append({"airport": airport, "lead": lead, "reveal": reveal,
                                   "tabs": visited, "exceptions": errors})
                    if errors:
                        return finish(checks)
    return finish(checks)


if __name__ == "__main__":
    raise SystemExit(main())

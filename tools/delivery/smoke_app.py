"""Functional app smoke; browser-side map tiles are outside this check."""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    os.environ["DASHBOARD_DATA_ROOT"] = str(args.root.resolve())
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(args.root / "app.py"), default_timeout=60).run()
    checks = [{"case": "initial", "exceptions": [x.message for x in app.exception]}]
    if not app.exception:
        for airport in ("KATL", "KDFW"):
            for lead in (3, 6, 12):
                for reveal in (False, True):
                    app.selectbox(key="airport").set_value(airport)
                    app.radio(key="horizon").set_value(lead)
                    app.toggle(key="reveal").set_value(reveal)
                    app.run()
                    checks.append({"airport": airport, "lead": lead, "reveal": reveal,
                                   "exceptions": [x.message for x in app.exception]})
                    if app.exception:
                        print(json.dumps({"status": "failed", "checks": checks}, indent=2))
                        return 1
    failed = any(c["exceptions"] for c in checks)
    print(json.dumps({"status": "failed" if failed else "passed", "checks": checks}, indent=2))
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())

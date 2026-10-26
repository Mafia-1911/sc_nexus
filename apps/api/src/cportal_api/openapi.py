"""Write the OpenAPI contract to docs/api/openapi.json (the web app generates types from it)."""

from __future__ import annotations

import json
import sys

from cportal_core.paths import repo_root

from cportal_api.main import create_app


def main() -> int:
    spec = create_app().openapi()
    out = repo_root() / "docs" / "api" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

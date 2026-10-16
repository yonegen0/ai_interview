"""Import-only qualification for the hosted CI image, before OIDC acquisition."""

import argparse
import json
from pathlib import Path

from .entrypoints import inspect


def qualify_ci(backend):
    backend = Path(backend).resolve()
    return inspect(
        [backend / "skills/p4", backend, backend / "src"],
        ["cloud_ci", "cloud_evidence"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", type=Path)
    args = parser.parse_args()
    result = qualify_ci(args.backend)
    # CI logs get finite status only, never import output or exception messages.
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "READY": False,
                "issue_codes": sorted({i["code"] for i in result["issues"]}),
            }
        )
    )
    raise SystemExit(0 if result["passed"] else 1)

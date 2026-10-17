"""Import-only qualification for the hosted CI image, before OIDC acquisition."""

import argparse
import json
import os
import sys
from pathlib import Path

from .entrypoints import inspect


def qualify_ci(backend):
    backend = Path(backend).resolve()
    return inspect(
        [backend / "skills/p4", backend, backend / "src"],
        ["cloud_ci", "cloud_evidence"],
    )


def persist_failure(backend):
    """Publish the existing bound finite schema; never export import details."""
    previous = sys.path[:]
    try:
        sys.path.insert(0, str(Path(backend).resolve() / "skills/p4"))
        from cloud_failure_json import persist

        persist("entry", "ModuleLoadFailed", "unknown", ValueError())
    finally:
        sys.path[:] = previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", type=Path)
    args = parser.parse_args()
    result = qualify_ci(args.backend)
    if not result["passed"] and os.environ.get("P4_CLOUD_FAILURE_JSON") == "true":
        try:
            persist_failure(args.backend)
        except Exception:
            result["issues"].append({"code": "EntrypointDiagnosticUnavailable"})
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
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

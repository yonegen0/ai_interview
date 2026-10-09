"""Decide whether package verification is needed without building an artifact."""

import json
import os
import re
import subprocess
from pathlib import Path

PACKAGE_PATHS = {
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/skills/p4/build_lambda.py",
    "backend/skills/p4/package_changes.py",
}


def needs_package(paths):
    return any(path.startswith("backend/src/") or path in PACKAGE_PATHS for path in paths)


def git(root, *args):
    return (
        subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )


def decision(root, event, event_name, head, explicit_base=""):
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("PackageComparisonHeadRequired")
    if event_name == "push":
        base = event.get("before", "")
        if base == "0" * 40:
            # A first branch push has no ancestor. Verify the whole package;
            # never guess a base or skip validation.
            if (
                event.get("created") is not True
                or event.get("deleted") is not False
                or event.get("after") != head
            ):
                raise ValueError("PackageComparisonBaseRequired")
            git(root, "cat-file", "-e", head + "^{commit}")
            return {
                "base": None,
                "head": head,
                "build_package": True,
                "reason": "new_branch_full_package_verification",
            }
    elif event_name == "pull_request":
        base = event.get("pull_request", {}).get("base", {}).get("sha", "")
    else:
        base = explicit_base
    if not re.fullmatch(r"[0-9a-f]{40}", base) or base == "0" * 40:
        raise ValueError("PackageComparisonBaseRequired")
    for revision in (base, head):
        git(root, "cat-file", "-e", revision + "^{commit}")
    if event_name == "pull_request":
        base = git(root, "merge-base", base, head)
    else:
        git(root, "merge-base", "--is-ancestor", base, head)
    paths = git(root, "diff", "--no-renames", "--name-only", "-z", base, head).split("\0")
    required = needs_package(paths)
    return {
        "base": base,
        "head": head,
        "build_package": required,
        "reason": "package_inputs_changed" if required else "package_inputs_unchanged",
    }


def main():
    try:
        result = decision(
            Path.cwd(),
            json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text()),
            os.environ["GITHUB_EVENT_NAME"],
            os.environ["GITHUB_SHA"],
            os.environ.get("PACKAGE_BASE_SHA", ""),
        )
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"build_package={str(result['build_package']).lower()}\n")
        print(json.dumps(result))
    except Exception:
        raise SystemExit(
            "PackageComparisonFailed: explicit available base/head commits required"
        ) from None


if __name__ == "__main__":
    main()

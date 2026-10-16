"""Pre-approval Python entrypoint qualification, with no application execution.

Syntax, import closure and literal subprocess targets are checked statically.
Selected entry modules are imported in an isolated child that denies network,
process creation, native-library calls, private reads and filesystem writes.
This is local qualification, not a substitute for Linux CI or execution consent.
"""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
from importlib.machinery import BuiltinImporter, FrozenImporter, PathFinder
from pathlib import Path

PYTHON = r"(?<![\w-])python(?:3(?:\.\d+)?)?"


def resolve(module, roots):
    if not isinstance(module, str) or not re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", module
    ):
        return None
    if module in sys.builtin_module_names:
        return {"kind": "stdlib", "path": None}
    if module == "os.path":
        module = os.path.__name__
    if module == "collections.abc":
        module = "_collections_abc"  # CPython 3.14 frozen stdlib alias.
    search = [str(p) for p in roots]
    spec = None
    name = ""
    for part in module.split("."):
        name = name + "." + part if name else part
        spec = (
            BuiltinImporter.find_spec(name)
            or FrozenImporter.find_spec(name)
            or PathFinder.find_spec(part, search)
        )
        if spec is None:
            return None
        search = list(spec.submodule_search_locations or [])
    origin = spec.origin
    if origin and origin not in {"built-in", "frozen"}:
        p = Path(origin).resolve()
        local = any(p.is_relative_to(r) for r in roots)
        return {"kind": "local" if local else "dependency", "path": str(p)}
    return {"kind": "namespace" if origin is None else "stdlib", "path": None}


def imports(tree, module, is_package):
    """All lexical imports, including lazy imports; platform conditions kept explicit."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = module.split(".") if is_package else module.split(".")[:-1]
                cut = node.level - 1
                parent = parent[: len(parent) - cut] if cut <= len(parent) else []
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if base:
                yield base, node.lineno
                # `from . import child` has no base module component.
                if node.module is None:
                    for alias in node.names:
                        yield base + "." + alias.name, node.lineno
        elif isinstance(node, ast.Call) and node.args:
            name = ast.unparse(node.func)
            if name in {"importlib.import_module", "__import__"} and isinstance(
                node.args[0], ast.Constant
            ):
                yield node.args[0].value, node.lineno


def commands(tree, owner):
    """Check literal Python -m targets, including the previously missed supervisor."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple)):
            continue
        for i, item in enumerate(node.elts[:-1]):
            if isinstance(item, ast.Constant) and item.value == "-m":
                target = node.elts[i + 1]
                if isinstance(target, ast.Constant) and isinstance(target.value, str):
                    yield target.value, node.lineno
                elif (
                    isinstance(target, ast.Attribute)
                    and ast.unparse(target) == "__spec__.name"
                ):
                    yield owner, node.lineno
                else:
                    yield None, node.lineno


def inspect(roots, entries, *, dependency_roots=(), probe=True):
    roots = [Path(r).resolve() for r in roots]
    dependency_roots = [Path(r).resolve() for r in dependency_roots]
    search = roots + dependency_roots + [Path(p) for p in sys.path if p]
    issues, checked, queue, seen, workers = [], [], list(entries), set(), []
    # Never execute scanned files to discover an entrypoint or a dependency.
    while queue:
        module = queue.pop(0)
        if module in seen:
            continue
        seen.add(module)
        for i in range(1, len(module.split("."))):
            queue.append(".".join(module.split(".")[:i]))
        found = resolve(module, search)
        if found is None:
            issues.append({"code": "ModuleMissing", "module": module})
            continue
        if found["path"] is None:
            continue
        path = Path(found["path"])
        if path.suffix != ".py" or not any(path.is_relative_to(r) for r in roots):
            continue
        try:
            if path.is_symlink() or any(
                p.is_symlink() or p.is_junction() for p in path.parents
            ):
                raise ValueError("ReparseSource")
            raw = path.read_bytes()
            tree = ast.parse(raw, filename=str(path))
            compile(tree, str(path), "exec")
        except (SyntaxError, OSError, ValueError):
            issues.append(
                {"code": "SourceInvalid", "module": module, "file": str(path)}
            )
            continue
        checked.append(
            {
                "module": module,
                "path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        for name, line in imports(tree, module, path.name == "__init__.py"):
            # Both platform modules are valid only on their corresponding host.
            if (
                name == "fcntl"
                and os.name == "nt"
                or name == "msvcrt"
                and os.name != "nt"
            ):
                continue
            found_import = resolve(name, search)
            if found_import is None:
                issues.append(
                    {
                        "code": "ImportMissing",
                        "module": module,
                        "import": name,
                        "line": line,
                    }
                )
            elif found_import["path"] and any(
                Path(found_import["path"]).is_relative_to(r) for r in roots
            ):
                queue.append(name)
        for target, line in commands(tree, module):
            workers.append({"owner": module, "target": target, "line": line})
            if target is None:
                issues.append(
                    {
                        "code": "DynamicWorkerRequiresDeclaration",
                        "module": module,
                        "line": line,
                    }
                )
            elif resolve(target, search) is None:
                issues.append(
                    {
                        "code": "WorkerModuleMissing",
                        "module": module,
                        "target": target,
                        "line": line,
                    }
                )
            else:
                queue.append(target)
    imported, denied, result = [], [], {}
    static_passed = not issues
    import_passed = None
    if probe and not issues:
        request = {
            "roots": [str(p) for p in roots + dependency_roots],
            "dependency_roots": [str(p) for p in dependency_roots]
            + [
                p
                for p in sys.path
                if p and Path(p).resolve().is_relative_to(Path(sys.prefix).resolve())
            ],
            "entries": [r["module"] for r in checked],
        }
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP"}
        }
        try:
            child = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(Path(__file__).with_name("import_probe.py")),
                ],
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
                env=env,
            )
            result = json.loads(child.stdout) if child.returncode == 0 else {}
            denied = result.get("denied_events", [])
            import_passed = result.get("passed") is True
            if result.get("passed") is not True:
                issues.append(
                    {
                        "code": "IsolatedImportRestricted"
                        if denied
                        else "IsolatedImportFailed",
                        "details": result.get("issues", [{"code": "ProbeUnavailable"}]),
                        "denied_events": denied,
                        "event_diagnostics": result.get("event_diagnostics", []),
                    }
                )
            imported = result.get("imported", [])
        except (subprocess.TimeoutExpired, ValueError, OSError):
            issues.append({"code": "ImportProbeUnavailable"})
    return {
        "passed": not issues,
        "issues": issues,
        "files": checked,
        "workers": workers,
        "imported": imported,
        "allowed_initializers": result.get("allowed_initializers", [])
        if probe and static_passed
        else [],
        "probe_requested": probe,
        "static_passed": static_passed,
        "import_passed": import_passed,
        "qualification": "host-local only; no application function, credential or external operation",
        "READY": False,
    }


def workflow(source):
    """Credential-free checks of literal Python commands and Actions dependency pins.

    This conservative line checker accepts the repository's block-run form. It is
    not a YAML parser: unsupported Python shell forms fail closed for review.
    """
    source = Path(source).resolve()
    issues, pins, scripts, inputs = [], [], [], []
    if not (source / ".github/workflows").is_dir():
        issues.append({"code": "WorkflowDirectoryMissing", "file": str(source)})
    for path in sorted((source / ".github/workflows").glob("*.y*ml")):
        inputs.append(
            {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
        working = source
        heredoc, body, start = None, [], 0
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if heredoc is not None:
                if stripped == heredoc:
                    try:
                        compile(textwrap.dedent("\n".join(body)), str(path), "exec")
                    except (SyntaxError, ValueError):
                        issues.append(
                            {
                                "code": "WorkflowInlinePythonInvalid",
                                "file": str(path),
                                "line": start,
                            }
                        )
                    heredoc, body = None, []
                else:
                    body.append(line)
                continue
            if stripped.startswith(("- name:", "- uses:")):
                working = source
            if stripped.startswith("working-directory:"):
                value = stripped.split(":", 1)[1].strip().strip("'\"")
                working = source / value
            if re.match(r"(?:-\s+)?uses:", stripped):
                value = stripped.split(":", 1)[1].split(" #", 1)[0].strip().strip("'\"")
                if value.startswith("./"):
                    if not (source / value).is_file():
                        issues.append(
                            {
                                "code": "ReusableWorkflowMissing",
                                "file": str(path),
                                "line": number,
                            }
                        )
                elif not re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", value):
                    issues.append(
                        {
                            "code": "ActionNotCommitPinned",
                            "file": str(path),
                            "line": number,
                        }
                    )
                else:
                    pins.append({"file": str(path), "line": number, "uses": value})
            if re.search(PYTHON + r"\s+", stripped):
                if "<<" in stripped:
                    match = re.search(r"<<\s*['\"]?([A-Za-z_]\w*)['\"]?\s*$", stripped)
                    if not match:
                        issues.append(
                            {
                                "code": "WorkflowPythonFormUnsupported",
                                "file": str(path),
                                "line": number,
                            }
                        )
                    else:
                        heredoc, start = match[1], number
                    continue
                match = re.search(PYTHON + r"\s+([\w./-]+\.py)\b", stripped)
                if match:
                    target = (working / match[1]).resolve()
                    scripts.append(str(target))
                    if not target.is_relative_to(source) or not target.is_file():
                        issues.append(
                            {
                                "code": "WorkflowScriptMissing",
                                "file": str(path),
                                "line": number,
                            }
                        )
                    else:
                        try:
                            compile(target.read_bytes(), str(target), "exec")
                        except (SyntaxError, ValueError):
                            issues.append(
                                {
                                    "code": "WorkflowScriptInvalid",
                                    "file": str(path),
                                    "line": number,
                                }
                            )
                else:
                    module = re.search(PYTHON + r"\s+-m\s+([\w.]+)\b", stripped)
                    if module:
                        if (
                            resolve(
                                module[1],
                                [
                                    working,
                                    working / "src",
                                    *[Path(p) for p in sys.path if p],
                                ],
                            )
                            is None
                        ):
                            issues.append(
                                {
                                    "code": "WorkflowModuleMissing",
                                    "file": str(path),
                                    "line": number,
                                }
                            )
                    elif not re.search(PYTHON + r"\s+(?:--version|-V)\b", stripped):
                        issues.append(
                            {
                                "code": "WorkflowPythonFormUnsupported",
                                "file": str(path),
                                "line": number,
                            }
                        )
        if heredoc is not None:
            issues.append(
                {
                    "code": "WorkflowPythonHeredocUnclosed",
                    "file": str(path),
                    "line": start,
                }
            )
    return {
        "passed": not issues,
        "issues": issues,
        "actions": pins,
        "scripts": scripts,
        "files": inputs,
        "limits": "line-based checks; runner/runtime/Linux imports still require CI",
        "READY": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--dependency-root", action="append", default=[])
    parser.add_argument("--entry", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root, args.entry, dependency_roots=args.dependency_root)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({"passed": report["passed"], "issues": report["issues"]}))
    raise SystemExit(0 if report["passed"] else 1)

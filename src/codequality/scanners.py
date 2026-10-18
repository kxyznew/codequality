"""Language detection and adapters for common quality scanners."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from codequality.model import Diagnostic, ScanReport

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "vendor",
    "target",
    "dist",
    "build",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
    ".codequality",
}


def _relative_path(path: str | Path | None, workspace: Path) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = workspace / candidate
    try:
        return candidate.resolve().relative_to(workspace.resolve()).as_posix()
    except (ValueError, OSError):
        return None


def _files(workspace: Path, suffixes: set[str]) -> list[Path]:
    found: list[Path] = []
    for directory, subdirs, filenames in os.walk(workspace):
        subdirs[:] = [name for name in subdirs if name not in IGNORED_DIRS]
        for filename in filenames:
            path = Path(directory, filename)
            if path.suffix.lower() in suffixes:
                found.append(path)
    return found


def _run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", "Scanner timed out after 300 seconds.")
    except OSError as exc:
        return subprocess.CompletedProcess(command, 125, "", str(exc))


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _location(item: dict[str, Any]) -> tuple[int | None, int | None, int | None, int | None]:
    start = item.get("location") or item.get("start") or {}
    end = item.get("end_location") or item.get("end") or {}
    return (
        start.get("row") or start.get("line"),
        start.get("column"),
        end.get("row") or end.get("line"),
        end.get("column"),
    )


def _scan_ruff(workspace: Path, repo_root: Path, report: ScanReport) -> None:
    python_files = _files(workspace, {".py", ".pyi"})
    if not python_files:
        return
    result = _run([sys.executable, "-m", "ruff", "check", ".", "--output-format=json"], workspace)
    if result is None:
        report.errors.append("Ruff is unavailable; reinstall Codequality with its package dependencies.")
        return
    report.scanners_run.append("Ruff (Python)")
    findings = _json(result.stdout) or []
    if isinstance(findings, list):
        for item in findings:
            row, column, end_row, end_column = _location(item)
            filename = Path(item.get("filename", ""))
            if filename and not filename.is_absolute():
                filename = workspace / filename
            report.diagnostics.append(
                Diagnostic(
                    tool="Ruff",
                    rule_id=str(item.get("code") or "RUFF"),
                    message=str(item.get("message") or "Python lint finding"),
                    level="warning",
                    path=_relative_path(filename, repo_root),
                    line=row,
                    column=column,
                    end_line=end_row,
                    end_column=end_column,
                )
            )
    if result.returncode not in (0, 1) and not findings:
        report.errors.append(f"Ruff could not scan the repository: {(result.stderr or result.stdout).strip()}")


def _has_eslint_config(workspace: Path) -> bool:
    names = {
        "eslint.config.js",
        "eslint.config.mjs",
        "eslint.config.cjs",
        "eslint.config.ts",
        ".eslintrc",
        ".eslintrc.js",
        ".eslintrc.cjs",
        ".eslintrc.json",
        ".eslintrc.yaml",
        ".eslintrc.yml",
    }
    if any((workspace / name).exists() for name in names):
        return True
    package_json = workspace / "package.json"
    if package_json.exists():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            return isinstance(package.get("eslintConfig"), dict)
        except (OSError, json.JSONDecodeError):
            return False
    return False


def _scan_eslint(workspace: Path, repo_root: Path, report: ScanReport) -> None:
    js_files = _files(workspace, {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"})
    if not js_files:
        return
    if not _has_eslint_config(workspace):
        report.notes.append("JavaScript/TypeScript files found; ESLint skipped because no ESLint config is present.")
        return

    local = workspace / "node_modules" / ".bin" / ("eslint.cmd" if os.name == "nt" else "eslint")
    executable = str(local) if local.exists() else shutil.which("eslint")
    if not executable:
        report.notes.append("ESLint config found, but ESLint is not installed locally or on PATH; skipped.")
        return

    command = [executable, "--format", "json", "."]
    if os.name == "nt" and executable.lower().endswith(".cmd"):
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/c", *command]
    result = _run(command, workspace)
    if result is None:
        report.notes.append("ESLint could not be started; skipped.")
        return
    report.scanners_run.append("ESLint (JavaScript/TypeScript)")
    payload = _json(result.stdout)
    if isinstance(payload, list):
        for file_result in payload:
            for item in file_result.get("messages", []):
                severity = int(item.get("severity") or 1)
                report.diagnostics.append(
                    Diagnostic(
                        tool="ESLint",
                        rule_id=str(item.get("ruleId") or "ESLINT"),
                        message=str(item.get("message") or "JavaScript/TypeScript lint finding"),
                        level="error" if severity >= 2 else "warning",
                        path=_relative_path(file_result.get("filePath"), repo_root),
                        line=item.get("line"),
                        column=item.get("column"),
                        end_line=item.get("endLine"),
                        end_column=item.get("endColumn"),
                    )
                )
    elif result.returncode not in (0, 1):
        report.errors.append(f"ESLint failed: {(result.stderr or result.stdout).strip()}")


GO_DIAGNOSTIC = re.compile(r"^(?P<file>.+?):(?P<line>\d+):(?P<column>\d+):\s*(?P<message>.+)$")


def _scan_go(workspace: Path, repo_root: Path, report: ScanReport) -> None:
    modules = [path.parent for path in _files(workspace, {".mod"}) if path.name == "go.mod"]
    if not modules:
        return
    executable = shutil.which("go")
    if not executable:
        report.notes.append("Go module found, but the Go toolchain is not installed; go vet skipped.")
        return
    for module in sorted(set(modules)):
        result = _run([executable, "vet", "./..."], module)
        if result is None:
            report.notes.append(f"go vet could not start in {module.relative_to(workspace).as_posix()}; skipped.")
            continue
        report.scanners_run.append(f"go vet ({module.relative_to(workspace).as_posix() or '.'})")
        diagnostics_before = len(report.diagnostics)
        output = "\n".join(part for part in (result.stdout, result.stderr) if part)
        for line in output.splitlines():
            match = GO_DIAGNOSTIC.match(line.strip())
            if not match:
                continue
            report.diagnostics.append(
                Diagnostic(
                    tool="Go vet",
                    rule_id="GO-VET",
                    message=match.group("message"),
                    level="warning",
                    path=_relative_path(
                        Path(match.group("file"))
                        if Path(match.group("file")).is_absolute()
                        else module / match.group("file"),
                        repo_root,
                    ),
                    line=int(match.group("line")),
                    column=int(match.group("column")),
                )
            )
        if result.returncode != 0 and len(report.diagnostics) == diagnostics_before:
            report.errors.append(f"go vet failed in {module.relative_to(workspace).as_posix() or '.'}: {output.strip()}")


def _scan_rust(workspace: Path, repo_root: Path, report: ScanReport) -> None:
    crates = [path.parent for path in _files(workspace, {".toml"}) if path.name == "Cargo.toml"]
    if not crates:
        return
    executable = shutil.which("cargo")
    if not executable:
        report.notes.append("Rust crate found, but Cargo is not installed; Clippy skipped.")
        return
    for crate in sorted(set(crates)):
        result = _run([executable, "clippy", "--all-targets", "--message-format=json"], crate)
        if result is None:
            report.notes.append(f"Clippy could not start in {crate.relative_to(workspace).as_posix()}; skipped.")
            continue
        report.scanners_run.append(f"Clippy ({crate.relative_to(workspace).as_posix() or '.'})")
        found = 0
        for line in result.stdout.splitlines():
            item = _json(line)
            if not isinstance(item, dict) or item.get("reason") != "compiler-message":
                continue
            message = item.get("message") or {}
            severity = message.get("level")
            if severity not in {"warning", "error"}:
                continue
            spans = message.get("spans") or []
            primary = next((span for span in spans if span.get("is_primary")), spans[0] if spans else {})
            report.diagnostics.append(
                Diagnostic(
                    tool="Clippy",
                    rule_id=(message.get("code") or {}).get("code") or "RUSTC",
                    message=str(message.get("message") or "Rust diagnostic"),
                    level=severity,
                    path=_relative_path(
                        Path(primary.get("file_name") or "")
                        if Path(primary.get("file_name") or "").is_absolute()
                        else crate / (primary.get("file_name") or ""),
                        repo_root,
                    ),
                    line=primary.get("line_start"),
                    column=primary.get("column_start"),
                    end_line=primary.get("line_end"),
                    end_column=primary.get("column_end"),
                )
            )
            found += 1
        if result.returncode != 0 and found == 0:
            report.errors.append(
                f"Clippy failed in {crate.relative_to(workspace).as_posix() or '.'}: "
                f"{(result.stderr or result.stdout).strip()}"
            )


def _scan_shell(workspace: Path, repo_root: Path, report: ScanReport) -> None:
    scripts = _files(workspace, {".sh"})
    if not scripts:
        return
    executable = shutil.which("shellcheck")
    if not executable:
        report.notes.append("Shell scripts found, but ShellCheck is not installed; skipped.")
        return
    result = _run([executable, "--format=json1", *[str(path) for path in scripts]], workspace)
    if result is None:
        report.notes.append("ShellCheck could not start; skipped.")
        return
    report.scanners_run.append("ShellCheck (shell)")
    payload = _json(result.stdout)
    if isinstance(payload, list):
        for item in payload:
            report.diagnostics.append(
                Diagnostic(
                    tool="ShellCheck",
                    rule_id=f"SC{item.get('code', '0000')}",
                    message=str(item.get("message") or "ShellCheck finding"),
                    level="error" if item.get("level") == "error" else "warning",
                    path=_relative_path(item.get("file"), repo_root),
                    line=item.get("line"),
                    column=item.get("column"),
                    end_line=item.get("endLine"),
                    end_column=item.get("endColumn"),
                )
            )
    elif result.returncode not in (0, 1):
        report.errors.append(f"ShellCheck failed: {(result.stderr or result.stdout).strip()}")


def scan(workspace: Path, repo_root: Path | None = None) -> ScanReport:
    """Run scanners for project types present in *workspace*."""
    repo_root = repo_root or workspace
    report = ScanReport()
    _scan_ruff(workspace, repo_root, report)
    _scan_eslint(workspace, repo_root, report)
    _scan_go(workspace, repo_root, report)
    _scan_rust(workspace, repo_root, report)
    _scan_shell(workspace, repo_root, report)
    return report

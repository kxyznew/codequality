"""Command-line interface for Codequality."""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from codequality import __version__
from codequality.sarif import write_sarif
from codequality.scanners import scan


def _write_github_output(name: str, value: str) -> None:
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _summary(report, sarif_path: Path, repo_root: Path) -> str:
    counts = Counter(item.level for item in report.diagnostics)
    lines = [
        "## Codequality",
        "",
        f"Scanners: {', '.join(report.scanners_run) if report.scanners_run else 'none available for detected project files'}",
        f"Findings: {len(report.diagnostics)} (errors: {counts['error']}, warnings: {counts['warning']})",
        f"SARIF: `{sarif_path.relative_to(repo_root).as_posix()}`",
    ]
    if report.diagnostics:
        lines.extend(["", "| Severity | Rule | Location | Finding |", "|---|---|---|---|"])
        for item in report.diagnostics[:100]:
            location = item.path or "repository"
            if item.line:
                location += f":{item.line}"
                if item.column:
                    location += f":{item.column}"
            lines.append(
                f"| {item.level} | {_markdown_cell(item.sarif_rule_id)} | "
                f"`{_markdown_cell(location)}` | {_markdown_cell(item.message)} |"
            )
        if len(report.diagnostics) > 100:
            lines.append(f"| … | … | … | {len(report.diagnostics) - 100} more findings are in the SARIF file. |")
    if report.notes:
        lines.extend(["", "### Scanner notes", ""])
        lines.extend(f"- {_markdown_cell(note)}" for note in report.notes)
    if report.errors:
        lines.extend(["", "### Scanner errors", ""])
        lines.extend(f"- {_markdown_cell(error)}" for error in report.errors)
    return "\n".join(lines) + "\n"


def _write_summary(markdown: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with Path(summary_file).open("a", encoding="utf-8") as handle:
            handle.write(markdown)
    print(markdown)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codequality",
        description="Detect project languages, run available scanners, and emit SARIF.",
    )
    parser.add_argument("--version", action="version", version=f"codequality {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    scan_parser = commands.add_parser("scan", help="scan a repository")
    scan_parser.add_argument("--workspace", type=Path, default=Path.cwd())
    scan_parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root for relative paths")
    scan_parser.add_argument("--sarif", type=Path, default=Path(".codequality/results.sarif"))
    scan_parser.add_argument("--fail-on", choices=("error", "warning", "none"), default="warning")
    return parser


def main() -> int:
    args = _parser().parse_args()
    workspace = args.workspace.resolve()
    repo_root = args.root.resolve()
    if not workspace.is_dir():
        print(f"Workspace directory does not exist: {workspace}", file=sys.stderr)
        return 2

    if not repo_root.is_dir():
        print(f"Repository root does not exist: {repo_root}", file=sys.stderr)
        return 2
    sarif_path = args.sarif if args.sarif.is_absolute() else repo_root / args.sarif
    sarif_path = sarif_path.resolve()
    try:
        sarif_path.relative_to(repo_root)
    except ValueError:
        print("SARIF output must be inside the workspace directory.", file=sys.stderr)
        return 2

    report = scan(workspace, repo_root)
    try:
        write_sarif(sarif_path, report.diagnostics)
    except OSError as exc:
        print(f"Could not write SARIF file: {exc}", file=sys.stderr)
        return 2

    markdown = _summary(report, sarif_path, repo_root)
    _write_summary(markdown)
    _write_github_output("findings-count", str(len(report.diagnostics)))
    _write_github_output("sarif-file", sarif_path.relative_to(repo_root).as_posix())

    if report.errors:
        return 2
    if args.fail_on == "error" and any(item.level == "error" for item in report.diagnostics):
        return 1
    if args.fail_on == "warning" and any(item.level in {"error", "warning"} for item in report.diagnostics):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

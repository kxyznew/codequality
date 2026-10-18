"""SARIF 2.1.0 serialization."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from codequality.model import Diagnostic


def build_sarif(diagnostics: list[Diagnostic]) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        rule_id = diagnostic.sarif_rule_id
        rules.setdefault(
            rule_id,
            {
                "id": rule_id,
                "shortDescription": {"text": f"{diagnostic.tool}: {diagnostic.rule_id}"},
            },
        )
        result: dict[str, Any] = {
            "ruleId": rule_id,
            "level": diagnostic.level,
            "message": {"text": diagnostic.message},
            "properties": {"scanner": diagnostic.tool},
        }
        if diagnostic.path:
            region: dict[str, int] = {}
            if diagnostic.line:
                region["startLine"] = max(1, int(diagnostic.line))
            if diagnostic.column:
                region["startColumn"] = max(1, int(diagnostic.column))
            if diagnostic.end_line:
                region["endLine"] = max(1, int(diagnostic.end_line))
            if diagnostic.end_colum:
                region["endColumn"] = max(1, int(diagnostic.end_column))
            location: dict[str, Any] = {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": quote(diagnostic.path.replace("\\", "/"), safe="/-._")
                    }
                }
            }
            if region:
                location["physicalLocation"]["region"] = region
            result["locations"] = [location]
            fingerprint_source = "\0".join(
                [diagnostic.sarif_rule_id, diagnostic.path, diagnostic.message]
            )
            result["partialFingerprints"] = {
                "primaryLocationLineHash": hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()
            }
        results.append(result)

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "Codequality", "rules": list(rules.values())}},
                "automationDetails": {"id": "codequality"},
                "results": results,
            }
        ],
    }


def write_sarif(path: Path, diagnostics: list[Diagnostic]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_sarif(diagnostics), indent=2) + "\n", encoding="utf-8")

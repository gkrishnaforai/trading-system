from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from app.fair_value_v2.schemas import MethodDefinition


@dataclass(frozen=True)
class MethodRegistry:
    definitions: Dict[str, MethodDefinition]
    selector: Optional[Dict[str, Any]] = None

    @classmethod
    def load_from_dir(cls, definitions_dir: str) -> "MethodRegistry":
        p = Path(definitions_dir)
        definitions: Dict[str, MethodDefinition] = {}

        selector: Optional[Dict[str, Any]] = None

        selector_path = p.parent / "selector.yaml"
        if selector_path.exists():
            try:
                selector = yaml.safe_load(selector_path.read_text())
            except Exception:
                selector = None

        for path in sorted(p.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text())
            definition = MethodDefinition.model_validate(raw)
            definitions[definition.method_key] = definition

        for path in sorted(p.glob("*.yml")):
            raw = yaml.safe_load(path.read_text())
            definition = MethodDefinition.model_validate(raw)
            definitions[definition.method_key] = definition

        return cls(definitions=definitions, selector=selector)

    def get(self, method_key: str) -> MethodDefinition:
        return self.definitions[method_key]

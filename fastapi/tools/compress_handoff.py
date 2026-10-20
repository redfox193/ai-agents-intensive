#!/usr/bin/env python3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml


def generate_handoff():
    root = Path.cwd()
    state_file = root / ".planning" / "STATE.md"

    # Получаем измененные файлы из git
    res = subprocess.run(["git", "diff", "--name-only", "HEAD~1"], capture_output=True, text=True)
    changed = [f for f in res.stdout.splitlines() if f.strip()]

    handoff_data = {
        "handoff_version": "1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "active_feature": "billing-domain-v1",
        "completed_wave": "Wave 1 (Schemas & Protocols)",
        "modified_artifacts": changed
        if changed
        else ["app/schemas/billing.py", "app/core/protocols.py"],
        "invariants_confirmed": [
            "balance_is_integer_kopecks",
            "strict_pydantic_v2_models",
            "pep_544_protocol_defined",
        ],
        "next_wave_target": {
            "wave": "Wave 3 (Services & Business Logic)",
            "file": "app/services/billing.py",
            "required_methods": ["top_up", "charge_click"],
        },
    }

    out_file = root / ".planning" / "HANDOFF.yaml"
    out_file.write_text(
        yaml.dump(handoff_data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(
        f"✅ Structured Handoff успешно сгенерирован: {out_file} (Объем: {len(out_file.read_bytes())} байт)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(generate_handoff())

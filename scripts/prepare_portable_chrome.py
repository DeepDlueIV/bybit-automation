from __future__ import annotations

from pathlib import Path

from bybit_automation.packaging.portable_chrome import prepare_portable_chrome


def main() -> int:
    root_dir = Path(__file__).resolve().parents[1]
    manifest_path = root_dir / "packaging" / "chrome-for-testing.json"
    destination = root_dir / "runtime" / "chrome-for-testing"
    executable = prepare_portable_chrome(manifest_path, destination)
    print(f"Portable Chrome готов: {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

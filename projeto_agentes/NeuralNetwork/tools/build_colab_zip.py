#!/usr/bin/env python3
"""Build a clean source ZIP that can be uploaded directly to the Colab notebook."""

from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
OUTPUT = ROOT / "projeto.zip"


def main():
    files = sorted(SOURCE.glob("*.py")) + [ROOT / "requirements.txt", ROOT / "README.md"]
    missing = [path for path in files if not path.is_file()]
    if missing:
        raise SystemExit("Required project files are missing: " + ", ".join(map(str, missing)))
    if not (SOURCE / "rodar_tudo.py").is_file():
        raise SystemExit("src/rodar_tudo.py is required in the Colab ZIP")

    with NamedTemporaryFile(dir=ROOT, suffix=".zip", delete=False) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as archive:
            for path in files:
                relative = path.relative_to(ROOT)
                archive.write(path, relative.as_posix())
        temporary_path.replace(OUTPUT)
    finally:
        temporary_path.unlink(missing_ok=True)

    print(f"Colab package created: {OUTPUT}")
    print(f"Included {len(files)} source and setup files.")


if __name__ == "__main__":
    main()

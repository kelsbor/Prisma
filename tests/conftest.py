"""Ambiente isolado para os testes: chaves, banco e índice descartáveis, sem internet."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["PRISMA_DIR"] = tempfile.mkdtemp(prefix="prisma-teste-")
os.environ["PRISMA_EMBEDDINGS"] = "falso"       # embeddings determinísticos, sem chamar o Gemini
os.environ.pop("ARMAZENAMENTO_URL", None)
os.environ.pop("GOOGLE_API_KEY", None)

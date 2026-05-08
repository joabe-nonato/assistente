from pathlib import Path


OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "deepseek-coder:6.7b"
DIRETORIO_RAIZ = Path.cwd()
LOG_FILE = "log.txt"
MEMORIA_FILE = DIRETORIO_RAIZ / "memoria.md"
MEMORIA_MAX_ENTRADAS = 8
MODO_DEBUG = False

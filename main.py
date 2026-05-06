import argparse
import json
import re
import sys
from pathlib import Path

import requests

from assistente import Contexto

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "deepseek-coder:6.7b"
DIRETORIO_RAIZ = Path.cwd()
LOG_FILE = "log.txt"


def log_separator(char: str = "-", length: int = 60):
    line = char * length
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def extract_tool_calls(text: str) -> list[dict]:
    pattern = r"```(?:executar_ferramenta|tool_call)\s*([\s\S]*?)```"
    blocks = re.findall(pattern, text)
    calls = []
    for block in blocks:
        try:
            calls.append(json.loads(block.strip()))
        except json.JSONDecodeError as e:
            calls.append({"_parse_error": str(e), "_raw": block.strip()})
    return calls


def normalize_tool_name(call: dict) -> str:
    return str(call.get("ferramenta") or call.get("action") or "").strip()


def dispatch_tool(call: dict) -> str:
    if "_parse_error" in call:
        msg = f"[ERRO parse JSON] {call['_parse_error']}\nRaw:\n{call.get('_raw')}"
        ctx.log(f"  [dispatch] {msg}")
        return msg

    tool_name = normalize_tool_name(call)
    fn = TOOL_MAP.get(tool_name)
    if not fn:
        msg = f"Ferramenta desconhecida: '{tool_name}'. Validas: {list(TOOL_MAP)}"
        ctx.log(f"  [dispatch] ERRO - {msg}")
        return f"[ERRO] {msg}"

    try:
        return fn(call)
    except KeyError as e:
        msg = f"Parametro ausente: {e} | payload: {call}"
        ctx.log(f"  [dispatch] ERRO - {msg}")
        return f"[ERRO] {msg}"
    except Exception as e:
        msg = f"{tool_name}: {e}"
        ctx.log(f"  [dispatch] ERRO - {msg}")
        return f"[ERRO] {msg}"


def normalize_path_text(path_str: str) -> str:
    texto = str(path_str or "").strip().strip('"').strip("'")
    texto = texto.replace("/", "\\")
    return texto


def resolve_path(path_str: str) -> Path:
    path_str = normalize_path_text(path_str)
    p = Path(path_str)
    if not p.is_absolute():
        p = DIRETORIO_RAIZ / p
    return p


def ferramenta_listar_arquivo(path: str) -> str:
    p = resolve_path(path)
    return ctx.listar_arquivos(p)


def ferramenta_executar_comando(comando: str, shell: str = "cmd") -> str:
    return ctx.executar_comando(comando, shell=shell, cwd=DIRETORIO_RAIZ)


def ferramenta_ler_arquivo(path: str) -> str:
    p = resolve_path(path)
    if ctx.arquivo_existe(p):
        return ctx.ler_arquivo(p)
    return f"[ERRO] Arquivo nao encontrado: {p}"


def ferramenta_excluir_arquivo(path: str) -> str:
    p = resolve_path(path)
    if ctx.arquivo_existe(p):
        return ctx.excluir_arquivo(p)
    return f"[ERRO] Arquivo nao encontrado: {p}"


def ferramenta_criar_arquivo(path: str, content: str) -> str:
    p = resolve_path(path)
    return ctx.substituir_arquivo(p, content)


def ferramenta_editar_arquivo(path: str, anchor: str, insert: str) -> str:
    p = resolve_path(path)
    if not p.exists():
        return f"[ERRO] Arquivo nao encontrado: {p}"

    text = p.read_text(encoding="utf-8")
    if anchor not in text:
        return f"[ERRO] Ancora '{anchor}' nao encontrada em {p}"

    text = text.replace(anchor, anchor + "\n" + insert, 1)
    return ctx.substituir_arquivo(p, text)


def ferramenta_mover_arquivo(origem: str, destino: str) -> str:
    return ctx.mover_arquivo(resolve_path(origem), resolve_path(destino))


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
TOOL_MAP = {
    "criar_arquivo": lambda d: ferramenta_criar_arquivo(d["path"], d["content"]),
    "editar_arquivo": lambda d: ferramenta_editar_arquivo(d["path"], d["anchor"], d["insert"]),
    "ler_arquivo": lambda d: ferramenta_ler_arquivo(d["path"]),
    "listar_arquivo": lambda d: ferramenta_listar_arquivo(d["path"]),
    "mover_arquivo": lambda d: ferramenta_mover_arquivo(d["origem"], d["destino"]),
    "executar_comando": lambda d: ferramenta_executar_comando(d["command"], d.get("shell", "cmd")),
}

# ---------------------------------------------------------------------------
# FERRAMENTAS do Assistente
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """voce e um assistente que faz manutencao e ajuda a organizar arquivos locais, com as ferramentas.

=== FERRAMENTAS ===
Para executar acoes no sistema de arquivos ou Git, inclua na sua resposta
um bloco no formato exato abaixo (um por vez):

```tool_call
{"action": "nome", ...parametros}
```

Acoes disponiveis:

Criar arquivo:
```tool_call
{"action":"criar_arquivo","path":"caminho/arquivo.cs","content":"conteudo completo aqui"}
```

Editar arquivo (inserir apos ancora):
```tool_call
{"action":"editar_arquivo","path":"caminho","anchor":"//texto_ancora","insert":"trecho novo"}
```

Ler arquivo:
```tool_call
{"action":"ler_arquivo","path":"caminho/arquivo"}
```

Listar diretorio:
```tool_call
{"action":"listar_arquivo","path":"caminho/pasta"}
```

Mover arquivo:
```tool_call
{"action":"mover_arquivo","origem":"caminho/origem","destino":"caminho/destino"}
```

Executar comando local no Windows:
```tool_call
{"action":"executar_comando","shell":"cmd","command":"dir caminho/arquivo"}
```

"""


def mode_interactive(ctx):
    log_separator()
    ctx.log("Inicio do processo")
    ctx.log(f"Modo: Interativo | Modelo: {OLLAMA_MODEL} | WorkDir: {DIRETORIO_RAIZ}")    
    ctx.log(" ")
    ctx.log("Digite o que deseja ou 'Sair' para encerrar")    
    log_separator()
    ctx.log("Em que posso ajudar?")
    
    while True:
        try:
            user_input = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            ctx.log("Processo encerrado pelo usuario.")
            break
        if user_input.lower() in ("sair", "exit", "quit"):
            ctx.log("Processo encerrado pelo usuario.")
            break
        if not user_input:
            continue
        ctx.log(f"Instrucao recebida: {user_input[:120]}")
        run_agent(user_input)
    
        


def chat_ollama(messages: list[dict], iteration: int) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": 0.2,
            "num_ctx": 8192,
            "num_predict": 4096,
        },
    }

    ctx.log(f"[Iteracao {iteration}] Enviando prompt ao Ollama (aguardando resposta sem limite de tempo)...")

    try:
        resp = requests.post(
            OLLAMA_URL,
            json=payload,
            stream=True,
            timeout=None,
        )
        resp.raise_for_status()
    except requests.exceptions.ConnectionError:
        ctx.log("[ERRO] Nao foi possivel conectar ao Ollama.")
        sys.exit(1)

    full_text = ""
    token_count = 0
    print()

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue

        chunk = data.get("message", {}).get("content", "")
        if chunk:
            print(chunk, end="", flush=True)
            full_text += chunk
            token_count += 1

        if data.get("done"):
            print()
            total_duration = data.get("total_duration", 0)
            eval_count = data.get("eval_count", token_count)
            if total_duration:
                segundos = total_duration / 1_000_000_000
                ctx.log(f"[Iteracao {iteration}] Resposta concluida | tokens: {eval_count} | tempo: {segundos:.1f}s")
            else:
                ctx.log(f"[Iteracao {iteration}] Resposta concluida | tokens: ~{token_count}")
            break

    ctx.log(full_text)
    return full_text


def run_agent(user_message: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    log_separator()
    ctx.log(f"Inicio do agente | Modelo: {OLLAMA_MODEL}")
    log_separator()

    for iteration in range(1, 50):
        assistant_text = chat_ollama(messages, iteration)

        if not assistant_text.strip():
            ctx.log(f"[Iteracao {iteration}] Resposta vazia. Encerrando.")
            break

        messages.append({"role": "assistant", "content": assistant_text})
        tool_calls = extract_tool_calls(assistant_text)

        if not tool_calls:
            log_separator()
            ctx.log("Execucao concluida com sucesso.")
            log_separator()
            return assistant_text

        results = []
        for call in tool_calls:
            tool_name = normalize_tool_name(call)
            ctx.log(f"  Executando ferramenta: {tool_name}")
            result = dispatch_tool(call)
            preview = result[:200] + ("..." if len(result) > 200 else "")
            ctx.log(f"  Resultado: {preview}")
            results.append(f"Resultado '{tool_name}':\n{result}")

        messages.append({
            "role": "user",
            "content": "\n\n".join(results),
        })

    ctx.log("[AVISO] Limite de iteracoes atingido.")
    return "[AVISO] Limite de iteracoes atingido."


def main():
    global ctx
    parser = argparse.ArgumentParser(description="Assistente - Ollama / DeepSeek local")
    parser.parse_args()
    ctx = Contexto()    
    mode_interactive(ctx)

if __name__ == "__main__":
    main()

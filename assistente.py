from datetime import datetime
from pathlib import Path
import os
import re
import shutil
import subprocess
from config import MODO_DEBUG

def resumir_texto(texto: str, limite: int) -> str:
    texto = re.sub(r"\s+", " ", str(texto or "").strip())
    if len(texto) <= limite:
        return texto
    return texto[: max(0, limite - 3)].rstrip() + "..."

def tem_extensao(caminho):
    return os.path.splitext(str(caminho))[1] != ""

def listar_sudiretorios(caminho_arquivo):
        p = Path(caminho_arquivo)
        
        if not p.exists():
            return f"[ERRO] Caminho nao encontrado: {p}"

        if p.is_file():
            stat = p.stat()
            return (
                f"ARQUIVO: {p.name}\n"
                f"Tamanho: {stat.st_size} bytes\n"
                f"Caminho: {p}"
            )

        itens = []
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            tipo = "DIR " if item.is_dir() else "FILE"
            itens.append(f"{tipo}: {caminho_arquivo}\\{item.name}")
            
        return itens

class Contexto:
    def __init__(self, arquivo_memoria, memoria_maxima):
        self.arquivo_memoria = arquivo_memoria
        self.memoria_maxima = memoria_maxima
        self.prompt = ""
        self.mensagem = ""
        self.memoria = ""
        self.lista_diretorios = []
        

    def __str__(self):
        return f"""
        prompt: {self.prompt}
        texto: {self.mensagem}
        acao: {self.memoria}
    """

    def data_hora(self):
        agora = datetime.now()
        return agora.strftime("%d/%m/%Y %H:%M")

    def log(self, texto):
        print(texto)
        if MODO_DEBUG:            
            self.gravar_arquivo("log.txt", f"{self.data_hora()} {texto}")

    def gravar_arquivo(self, caminho_arquivo, texto):
        with open(caminho_arquivo, "a", encoding="utf-8") as arquivo:
            arquivo.write(f"{texto}\n")

    def substituir_arquivo(self, caminho_arquivo, texto):
        caminho = Path(caminho_arquivo)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return f"[OK] Arquivo salvo: {caminho}"

    def ler_arquivo(self, caminho):
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                with open(caminho, "r", encoding=encoding) as arquivo:
                    return arquivo.read()
            except UnicodeDecodeError:
                continue
        return f"[ERRO] Nao foi possivel ler o arquivo: {caminho}"

    def arquivo_existe(self, caminho_arquivo):
        return Path(caminho_arquivo).exists()
    
    def listar_diretorios(self, caminho_arquivo):
        p = Path(caminho_arquivo)
        
        if not p.exists():
            return f"[ERRO] Caminho nao encontrado: {p}"

        if p.is_file():
            stat = p.stat()
            return (
                f"ARQUIVO: {p.name}\n"
                f"Tamanho: {stat.st_size} bytes\n"
                f"Caminho: {p}"
            )

        itens = []
        for item in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            tipo = "DIR " if item.is_dir() else "FILE"
            itens.append(f"{tipo}: {p}\\{item.name}")
            if item.is_dir():
                self.lista_diretorios.append(item.name)
            
        for subdiretorio in self.lista_diretorios:
            sublista = listar_sudiretorios(f"{p}\\{subdiretorio}")
            for subitem in sublista:
                itens.append(subitem)

        return "\n".join(itens) if itens else f"[OK] Pasta vazia: {p}"

    def _ler_texto_arquivo_seguro(self, caminho):
        for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
            try:
                with open(caminho, "r", encoding=encoding) as arquivo:
                    return arquivo.read()
            except UnicodeDecodeError:
                continue
        return None

    def concatenar_arquivos(self, arquivos, caminho_destino, separador="\n\n"):
        destino = Path(caminho_destino)
        destino.parent.mkdir(parents=True, exist_ok=True)

        arquivos_validos = []
        erros = []

        for item in arquivos or []:
            caminho = Path(item)
            if not caminho.exists() or not caminho.is_file():
                erros.append(f"[ERRO] Arquivo nao encontrado: {caminho}")
                continue

            texto = self._ler_texto_arquivo_seguro(caminho)
            if texto is None:
                erros.append(f"[ERRO] Nao foi possivel ler o arquivo: {caminho}")
                continue

            arquivos_validos.append((caminho, texto))

        if not arquivos_validos:
            if erros:
                return "\n".join(erros)
            return "[ERRO] Nenhum arquivo valido foi informado."

        blocos = []
        for caminho, texto in arquivos_validos:
            blocos.append(f"### {caminho}\n{texto}")

        destino.write_text(separador.join(blocos), encoding="utf-8")

        resposta = [f"[OK] Arquivo salvo: {destino}"]
        resposta.append(f"[OK] Arquivos concatenados: {len(arquivos_validos)}")
        if erros:
            resposta.extend(erros)
        return "\n".join(resposta)

    def copiar_conteudo_diretorio(self, diretorio_origem, caminho_destino, recursivo=True, separador="\n\n"):
        origem = Path(diretorio_origem)
        if not origem.exists():
            return f"[ERRO] Caminho nao encontrado: {origem}"

        destino = Path(caminho_destino)
        destino.parent.mkdir(parents=True, exist_ok=True)

        if origem.is_file():
            return self.concatenar_arquivos([origem], destino, separador=separador)

        if recursivo:
            candidatos = [p for p in origem.rglob("*") if p.is_file()]
        else:
            candidatos = [p for p in origem.iterdir() if p.is_file()]

        try:
            destino_resolvido = destino.resolve()
        except Exception:
            destino_resolvido = destino

        arquivos = []
        for caminho in candidatos:
            try:
                if caminho.resolve() == destino_resolvido:
                    continue
            except Exception:
                pass
            arquivos.append(caminho)

        arquivos = sorted(
            arquivos,
            key=lambda p: str(p.relative_to(origem) if p.is_relative_to(origem) else p).lower(),
        )

        return self.concatenar_arquivos(arquivos, destino, separador=separador)

    def copiar_arquivos_para_texto(self, destino, arquivos=None, diretorio=None, recursivo=True, separador="\n\n"):
        if arquivos:
            return self.concatenar_arquivos(arquivos, destino, separador=separador)

        if diretorio:
            return self.copiar_conteudo_diretorio(diretorio, destino, recursivo=recursivo, separador=separador)

        return "[ERRO] Informe 'arquivos' ou 'diretorio'."

    def mover_arquivo(self, origem, destino):
        origem = Path(origem)
        destino = Path(destino)

        if not origem.exists():
            return f"[ERRO] Origem nao encontrada: {origem}"

        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origem), str(destino))
        return f"[OK] Arquivo movido: {origem} -> {destino}"

    def excluir_arquivo(self, caminho_arquivo):
        p = Path(caminho_arquivo)
        if p.exists() and p.is_file():
            p.unlink()
            return f"[OK] Arquivo excluido: {p}"
        return f"[ERRO] Arquivo nao encontrado: {p}"

    def executar_comando(self, comando, shell="cmd", cwd=None):
        comando = str(comando or "").strip()
        if not comando:
            return "[ERRO] Comando vazio."

        if shell == "powershell":
            args = ["powershell.exe", "-NoProfile", "-Command", comando]
            use_shell = False
        elif shell == "cmd":
            args = ["cmd.exe", "/c", comando]
            use_shell = False
        else:
            args = comando
            use_shell = True

        resultado = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            shell=use_shell,
        )

        saida = (resultado.stdout or "").strip()
        erro = (resultado.stderr or "").strip()

        partes = [f"[OK] exit_code={resultado.returncode}"]
        if saida:
            partes.append("STDOUT:\n" + saida)
        if erro:
            partes.append("STDERR:\n" + erro)

        return "\n\n".join(partes)

    def excluir_todos_arquivos_diretorio(self, caminho_diretorio):
        if os.path.isdir(caminho_diretorio):
            shutil.rmtree(caminho_diretorio)

# ---------------------------------------------------------------------------
# MEMÓRIA
# ---------------------------------------------------------------------------

    def inicializar_memoria(self):
        self.arquivo_memoria.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo_memoria.write_text("# Memória da sessão\n\n", encoding="utf-8")


    def carregar_memoria(self) -> str:
        if not self.arquivo_memoria.exists():
            return ""

        linhas = self.arquivo_memoria.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith("- ") for line in linhas):
            return ""

        return "\n".join(linhas).strip()


    def registrar_memoria(self, user_message: str, tool_names: list[str], assistant_text: str):
        entradas = []
        if self.arquivo_memoria.exists():
            for line in self.arquivo_memoria.read_text(encoding="utf-8").splitlines():
                if line.startswith("- "):
                    entradas.append(line)

        ferramentas = ", ".join(dict.fromkeys(tool_names)) if tool_names else "nenhuma ferramenta"
        entrada = (
            f"- Pedido: {resumir_texto(user_message, 220)} | "
            f"Ferramentas: {ferramentas} | "
            f"Resultado: {resumir_texto(assistant_text, 440)}"
        )
        entradas.append(entrada)
        entradas = entradas[-self.memoria_maxima:]

        conteudo = "# Memória da sessão\n\n"
        if entradas:
            conteudo += "\n".join(entradas) + "\n"
        self.arquivo_memoria.write_text(conteudo, encoding="utf-8")
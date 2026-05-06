from datetime import datetime
from pathlib import Path
import os
import shutil
import subprocess


def tem_extensao(caminho):
    return os.path.splitext(str(caminho))[1] != ""


class Contexto:
    def __init__(self):
        self.prompt = ""
        self.texto = ""
        self.acao = ""

    def __str__(self):
        return f"""
        prompt: {self.prompt}
        texto: {self.texto}
        acao: {self.acao}
    """

    def data_hora(self):
        agora = datetime.now()
        return agora.strftime("%d/%m/%Y %H:%M")

    def log(self, texto):
        print(texto)
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

    def listar_arquivos(self, caminho_arquivo):
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
            itens.append(f"{tipo}  {item.name}")

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

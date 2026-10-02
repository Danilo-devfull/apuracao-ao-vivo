"""Lista oficial de candidatos por estado, usada só para mostrar o nome na colinha.

Formato salvo em dados/candidatos/<uf>.json:
    {"pres": {"13": ["NOME DE URNA", "SIGLA"]}, "gov": {...}, "sen": {...}, "depfed": {...}, "depest": {...}}

O celular baixa o arquivo do estado inteiro e procura o número localmente:
o número digitado pelo eleitor nunca é enviado ao servidor.
"""
import json
import re
from django.conf import settings

# código do cargo no TSE -> chave usada na colinha
CARGOS = {1: "pres", 3: "gov", 5: "sen", 6: "depfed", 7: "depest", 8: "depest"}
FORA = re.compile(r"INDEFERID|CANCELAD|RENÚNCIA|RENUNCIA|FALECID|CASSAD|NÃO CONHECID|NAO CONHECID", re.I)
_SO_DIGITOS = re.compile(r"^\d{2,5}$")


def caminho(uf):
    return settings.CANDIDATOS_DIR / f"{uf}.json"


def limpar(texto, limite=60):
    return re.sub(r"\s+", " ", str(texto or "")).strip()[:limite]


def adicionar(dados, cargo_tse, numero, nome, partido, situacao=""):
    chave = CARGOS.get(int(cargo_tse))
    numero = str(numero or "").strip()
    if not chave or not _SO_DIGITOS.match(numero) or FORA.search(str(situacao or "")):
        return
    dados.setdefault(chave, {})[numero] = [limpar(nome), limpar(partido, 20)]


def salvar(uf, dados):
    settings.CANDIDATOS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = caminho(uf).with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(caminho(uf))    # troca atômica: nunca serve um arquivo pela metade


def ler(uf):
    try:
        return caminho(uf).read_bytes()
    except FileNotFoundError:
        return None
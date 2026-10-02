"""Busca e normaliza os resultados oficiais do TSE.

Quem consulta o TSE é SÓ o processo `python manage.py atualizar_tse`, que roda em
segundo plano. As páginas do site apenas leem o último resultado guardado no Redis.
Assim, um pico de acessos nunca vira um pico de chamadas ao TSE, e uma lentidão do
TSE nunca trava o site.

Formato de referência: "dados-simplificados" de 2022
  {base}/{eleicao}/dados-simplificados/{uf}/{uf}-c{cargo}-e{eleicao:06}-r.json
Confira o formato de 2026 assim que o TSE publicar e ajuste _normalizar() se mudar.
"""
import json
import logging
import re
import time
import requests
from django.conf import settings
from django.core.cache import cache

log = logging.getLogger(__name__)

UFS = {
    "ac": "Acre", "al": "Alagoas", "ap": "Amapá", "am": "Amazonas", "ba": "Bahia",
    "ce": "Ceará", "df": "Distrito Federal", "es": "Espírito Santo", "go": "Goiás",
    "ma": "Maranhão", "mt": "Mato Grosso", "ms": "Mato Grosso do Sul", "mg": "Minas Gerais",
    "pa": "Pará", "pb": "Paraíba", "pr": "Paraná", "pe": "Pernambuco", "pi": "Piauí",
    "rj": "Rio de Janeiro", "rn": "Rio Grande do Norte", "rs": "Rio Grande do Sul",
    "ro": "Rondônia", "rr": "Roraima", "sc": "Santa Catarina", "sp": "São Paulo",
    "se": "Sergipe", "to": "Tocantins",
}
TOP = 5
MAX_BYTES = 20 * 1024 * 1024  # recusa respostas absurdamente grandes
_SO_DIGITOS = re.compile(r"^\d{1,20}$")

_sessao = requests.Session()
_sessao.headers["User-Agent"] = "apuracao-informativa/1.0"


def cargos_para(uf):
    if uf == "df":
        estadual = ("0008", "Deputado distrital")
    else:
        estadual = ("0007", "Deputado estadual")
    return [
        ("0001", "Presidente", "federal"),
        ("0003", "Governador", "estadual"),
        ("0005", "Senador", "estadual"),
        ("0006", "Deputado federal", "estadual"),
        (estadual[0], estadual[1], "estadual"),
    ]


def _num(valor):
    """'48,43' -> 48.43 ; '1234567' -> 1234567 ; lixo -> 0"""
    texto = str(valor or "").strip()
    try:
        if "," in texto:
            return float(texto.replace(".", "").replace(",", "."))
        return int(texto) if texto else 0
    except ValueError:
        return 0


def _texto(valor, limite=80):
    return str(valor or "")[:limite]


def _eleicao(tipo):
    codigo = settings.TSE_ELEICAO_FEDERAL if tipo == "federal" else settings.TSE_ELEICAO_ESTADUAL
    return str(int(codigo)), str(int(codigo)).zfill(6)


def _baixar_json(url):
    with _sessao.get(url, timeout=(5, 20), stream=True) as r:
        r.raise_for_status()
        dados = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(dados) > MAX_BYTES:
        raise ValueError("resposta do TSE maior que o limite")
    return json.loads(dados)


def _normalizar(uf, nome, curto, dados):
    candidatos = []
    for c in dados.get("cand", []) or []:
        sq = str(c.get("sqcand") or "")
        foto = f"{settings.TSE_BASE_URL}/{curto}/fotos/{uf}/{sq}.jpeg" if _SO_DIGITOS.match(sq) else None
        candidatos.append({
            "numero": _texto(c.get("n"), 10),
            "nome": _texto(c.get("nm")),
            "partido": _texto(c.get("cc"), 120),
            "votos": _num(c.get("vap")),
            "percentual": _num(c.get("pvap")),
            "eleito": c.get("e") == "s",
            "situacao": _texto(c.get("st"), 40),
            "foto": foto,
        })
    candidatos.sort(key=lambda x: x["votos"], reverse=True)
    return {
        "cargo": nome,
        "secoes_apuradas": _num(dados.get("pst")),
        "atualizado": _texto(f"{dados.get('dg', '')} {dados.get('hg', '')}".strip(), 30),
        "total_candidatos": len(candidatos),
        "candidatos": candidatos[:TOP],
    }


def atualizar_estado(uf):
    """Busca os 5 cargos de um estado no TSE e grava no cache. Usado só pelo worker."""
    chave = f"tse:{uf}"
    anterior = {c["cargo"]: c for c in (cache.get(chave) or {}).get("cargos", [])}
    cargos = []
    for codigo, nome, tipo in cargos_para(uf):
        curto, longo = _eleicao(tipo)
        url = f"{settings.TSE_BASE_URL}/{curto}/dados-simplificados/{uf}/{uf}-c{codigo}-e{longo}-r.json"
        try:
            cargos.append(_normalizar(uf, nome, curto, _baixar_json(url)))
        except Exception as exc:
            log.warning("TSE indisponível para %s/%s: %s", uf, codigo, exc)
            # Mantém o último resultado bom em vez de apagar a tela do eleitor
            cargos.append(anterior.get(nome) or {"cargo": nome, "indisponivel": True, "candidatos": []})
    cache.set(chave, {"uf": uf, "estado": UFS[uf], "cargos": cargos, "gerado_em": int(time.time())}, None)


def resultados(uf):
    """Usado pelas páginas: só lê o cache, nunca chama o TSE."""
    return cache.get(f"tse:{uf}") or {
        "uf": uf, "estado": UFS[uf], "aguardando": True,
        "cargos": [{"cargo": n, "indisponivel": True, "candidatos": []} for _, n, _ in cargos_para(uf)],
    }
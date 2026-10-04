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
    with _sessao.get(url, timeout=(4, 8), stream=True) as r:
        r.raise_for_status()
        dados = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(dados) > MAX_BYTES:
        raise ValueError("resposta do TSE maior que o limite")
    return json.loads(dados)


def _url(uf, codigo, tipo):
    """Formato 2026 (arquivo de resultado unificado EA20):
    {base}/{eleicao}/dados/{uf}/{uf}-c{cargo:4}-e{eleicao:6}-u.json"""
    curto, longo = _eleicao(tipo)
    return f"{settings.TSE_BASE_URL}/{curto}/dados/{uf}/{uf}-c{codigo}-e{longo}-u.json", curto


def _candidatos_ea20(dados, codigo):
    """Percorre carg > agr > par > cand do EA20 e devolve (candidato, sigla do partido)."""
    for cargo in dados.get("carg", []) or []:
        if str(cargo.get("cd", "")).lstrip("0") != codigo.lstrip("0"):
            continue
        for agr in cargo.get("agr", []) or []:
            for par in agr.get("par", []) or []:
                for c in par.get("cand", []) or []:
                    yield c, par.get("sg") or ""


def _normalizar(uf, nome, curto, dados, codigo):
    candidatos = []
    origem = list(_candidatos_ea20(dados, codigo))
    if not origem:   # formato antigo (2022), por compatibilidade
        origem = [(c, c.get("cc", "")) for c in dados.get("cand", []) or []]
    for c, partido in origem:
        sq = str(c.get("sqcand") or "")
        foto = f"{settings.TSE_BASE_URL}/{curto}/fotos/{uf}/{sq}.jpeg" if _SO_DIGITOS.match(sq) else None
        situacao = _texto(c.get("st"), 40)
        candidatos.append({
            "numero": _texto(c.get("n"), 10),
            "nome": _texto(c.get("nmu") or c.get("nm")),
            "partido": _texto(partido, 40),
            "votos": _num(c.get("vap")),
            "percentual": _num(c.get("pvap")),
            "eleito": situacao.lower().startswith("eleito"),
            "situacao": situacao if situacao and situacao != "Não eleito" else "",
            "foto": foto,
        })
    candidatos.sort(key=lambda x: x["votos"], reverse=True)
    s = dados.get("s") or {}
    return {
        "cargo": nome,
        "secoes_apuradas": _num(s.get("pst") or dados.get("pst")),
        "atualizado": _texto(f"{dados.get('dg', '')} {dados.get('hg', '')}".strip(), 30),
        "total_candidatos": len(candidatos),
        "candidatos": candidatos[:TOP],
    }


def buscar_estado(uf, anterior=None):
    """Busca os 5 cargos de um estado no TSE (em paralelo) e devolve o resultado pronto."""
    from concurrent.futures import ThreadPoolExecutor
    anterior = {c["cargo"]: c for c in (anterior or {}).get("cargos", [])}

    def um(item):
        codigo, nome, tipo = item
        # Presidente: resultado nacional (arquivo "br"), igual para todos os estados
        abr = "br" if codigo == "0001" else uf
        if abr == "br":
            guardado = cache.get("tse:br:presidente")
            if guardado and time.time() - guardado.get("_em", 0) < settings.TSE_INTERVALO_SEGUNDOS:
                return {k: v for k, v in guardado.items() if k != "_em"}
        url, curto = _url(abr, codigo, tipo)
        try:
            r = _normalizar(abr, nome, curto, _baixar_json(url), codigo)
            if abr == "br":
                r["abrangencia"] = "Brasil"
                cache.set("tse:br:presidente", {**r, "_em": time.time()}, 3600)
            return r
        except Exception as exc:
            log.warning("TSE indisponível para %s/%s: %s", uf, codigo, exc)
            return anterior.get(nome) or {"cargo": nome, "indisponivel": True, "candidatos": []}

    with ThreadPoolExecutor(max_workers=5) as pool:
        cargos = list(pool.map(um, cargos_para(uf)))
    return {"uf": uf, "estado": UFS[uf], "cargos": cargos, "gerado_em": int(time.time())}


def atualizar_estado(uf):
    """Usado pelo worker (servidor próprio): busca e grava no cache sem expirar."""
    chave = f"tse:{uf}"
    cache.set(chave, buscar_estado(uf, cache.get(chave)), None)


def _aguardando(uf):
    return {"uf": uf, "estado": UFS[uf], "aguardando": True,
            "cargos": [{"cargo": n, "indisponivel": True, "candidatos": []} for _, n, _ in cargos_para(uf)]}


def resultados(uf):
    """Usado pelas páginas.
    - Servidor próprio (com worker): só lê o cache.
    - Vercel (sem worker): busca no TSE na hora, guarda por alguns segundos, e o CDN da
      Vercel segura o resto. Antes do horário da apuração não consulta o TSE (evita 404s,
      que podem bloquear o IP)."""
    if not settings.BUSCA_SOB_DEMANDA:
        return cache.get(f"tse:{uf}") or _aguardando(uf)
    from datetime import datetime
    if datetime.now().astimezone() < datetime.fromisoformat(settings.APURACAO_INICIO):
        return _aguardando(uf)
    chave = f"tse:{uf}"
    atual = cache.get(chave)
    if atual and time.time() - atual.get("gerado_em", 0) < settings.TSE_INTERVALO_SEGUNDOS:
        return atual
    novo = buscar_estado(uf, atual)
    cache.set(chave, novo, 3600)
    return novo
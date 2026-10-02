"""Baixa a lista oficial de candidatos (número, nome de urna, partido) para a colinha.

    python manage.py baixar_candidatos --listar-eleicoes
        mostra as eleições do DivulgaCandContas, para achar o código de 2026

    python manage.py baixar_candidatos
        baixa os 27 estados pelo DivulgaCandContas (precisa de TSE_CAND_ELEICAO no .env)

    python manage.py baixar_candidatos --csv consulta_cand_2026_BRASIL.csv
        plano B: usa o arquivo do Portal de Dados Abertos do TSE

Rode de novo no sábado para pegar candidaturas indeferidas ou substituídas.
"""
import csv
import json
import time
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apuracao.candidatos import CARGOS, adicionar, salvar
from apuracao.tse import UFS

MAX_BYTES = 20 * 1024 * 1024


def baixar(url):
    with requests.get(url, timeout=(5, 30), stream=True, headers={"User-Agent": "apuracao-informativa/1.0"}) as r:
        r.raise_for_status()
        corpo = r.raw.read(MAX_BYTES + 1, decode_content=True)
    if len(corpo) > MAX_BYTES:
        raise ValueError("resposta grande demais")
    return json.loads(corpo)


class Command(BaseCommand):
    help = "Baixa a lista oficial de candidatos para a busca da colinha"

    def add_arguments(self, parser):
        parser.add_argument("--listar-eleicoes", action="store_true")
        parser.add_argument("--csv", help="arquivo consulta_cand_<ano>_*.csv do Portal de Dados Abertos")

    def handle(self, *args, **o):
        if o["listar_eleicoes"]:
            return self.listar()
        if o["csv"]:
            return self.do_csv(o["csv"])
        return self.do_divulga()

    # ---------- descobrir o código da eleição ----------
    def listar(self):
        url = f"{settings.TSE_CAND_BASE}/eleicao/ordinarias"
        try:
            dados = baixar(url)
        except Exception as e:
            raise CommandError(f"Não consegui acessar {url}: {e}")
        for e in dados if isinstance(dados, list) else dados.get("eleicoes", []):
            self.stdout.write(f"ano={e.get('ano')}  código={e.get('id')}  {e.get('nomeEleicao') or e.get('descricaoEleicao') or ''}")
        self.stdout.write("\nColoque o código da eleição geral de 2026 em TSE_CAND_ELEICAO no .env.")

    # ---------- DivulgaCandContas ----------
    def do_divulga(self):
        if not settings.TSE_CAND_ELEICAO.isdigit():
            raise CommandError("Defina TSE_CAND_ELEICAO no .env (descubra com --listar-eleicoes).")
        base, ano, ele = settings.TSE_CAND_BASE, settings.TSE_CAND_ANO, settings.TSE_CAND_ELEICAO

        def lista(uf_api, cargo):
            url = f"{base}/candidatura/listar/{ano}/{uf_api}/{ele}/{cargo}/candidatos"
            d = baixar(url)
            return d.get("candidatos", []) if isinstance(d, dict) else []

        def registrar(dados, cargo, c):
            partido = c.get("partido") or {}
            adicionar(dados, cargo, c.get("numero"), c.get("nomeUrna") or c.get("nomeCompleto"),
                      partido.get("sigla") if isinstance(partido, dict) else partido,
                      c.get("descricaoSituacao") or c.get("descricaoTotalizacao") or "")

        try:
            presidentes = lista("BR", 1)
        except Exception as e:
            raise CommandError(f"Falhou ao buscar presidente: {e}\nSe o endereço mudou, use o plano B (--csv).")
        ok = 0
        for uf in UFS:
            dados = {}
            for c in presidentes:
                registrar(dados, 1, c)
            for cargo in (3, 5, 6, 8 if uf == "df" else 7):
                try:
                    for c in lista(uf.upper(), cargo):
                        registrar(dados, cargo, c)
                except Exception as e:
                    self.stderr.write(f"  {uf.upper()} cargo {cargo}: {e}")
                time.sleep(0.3)   # educado com o servidor do TSE
            salvar(uf, dados)
            ok += 1
            self.stdout.write(f"{uf.upper()}: " + ", ".join(f"{k}={len(v)}" for k, v in dados.items()))
        self.stdout.write(self.style.SUCCESS(f"Listas salvas para {ok} estados em {settings.CANDIDATOS_DIR}"))

    # ---------- Plano B: CSV do Portal de Dados Abertos ----------
    def do_csv(self, arquivo):
        por_uf = {uf: {} for uf in UFS}
        presidentes = {}
        with open(arquivo, encoding="latin-1", newline="") as f:
            for l in csv.DictReader(f, delimiter=";"):
                try:
                    cargo = int(l.get("CD_CARGO", 0))
                except ValueError:
                    continue
                if cargo not in CARGOS:
                    continue
                situacao = " ".join(l.get(k, "") for k in ("DS_SITUACAO_CANDIDATURA", "DS_DETALHE_SITUACAO_CAND", "DS_SIT_TOT_TURNO"))
                args = (cargo, l.get("NR_CANDIDATO"), l.get("NM_URNA_CANDIDATO"), l.get("SG_PARTIDO"), situacao)
                uf = (l.get("SG_UF") or "").lower()
                if cargo == 1:
                    adicionar(presidentes, *args)
                elif uf in por_uf:
                    adicionar(por_uf[uf], *args)
        for uf, dados in por_uf.items():
            if presidentes:
                dados["pres"] = presidentes.get("pres", {})
            salvar(uf, dados)
            self.stdout.write(f"{uf.upper()}: " + ", ".join(f"{k}={len(v)}" for k, v in dados.items()))
        self.stdout.write(self.style.SUCCESS("Listas salvas a partir do CSV."))
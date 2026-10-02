"""Preenche o cache com uma apuração FICTÍCIA para testar o visual localmente.

    python manage.py simular_apuracao          # todos os estados
    python manage.py simular_apuracao --limpar # apaga a simulação

Nomes, partidos e números são inventados. Nunca rode isto em produção.
"""
import random
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from apuracao.tse import UFS, cargos_para
from apuracao.candidatos import salvar, caminho

NOMES = ["Ana Ribeiro", "Caio Menezes", "Breno Lima", "Sônia Prado", "Rafael Duarte", "Lúcia Ferreira",
         "Jonas Teixeira", "Helena Costa", "Jorge Santana", "Renata Nunes", "Marcelo Brito", "Antônio Reis",
         "Cláudia Moura", "Edson Matos", "Mariana Vieira", "Tomás Braga", "Diego Barros", "Patrícia Rocha",
         "Felipe Cardoso", "Juliana Teixeira", "Marcelo Viana", "Tatiane Brito", "André Lopes", "Camila Freitas"]
DIGITOS = {"0001": 2, "0003": 2, "0005": 3, "0006": 4, "0007": 5, "0008": 5}


class Command(BaseCommand):
    help = "Simula uma apuração fictícia no cache (só para desenvolvimento)"

    def add_arguments(self, parser):
        parser.add_argument("--limpar", action="store_true")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Recusado: a simulação só roda com DEBUG=1 (desenvolvimento).")
        if opts["limpar"]:
            for uf in UFS:
                cache.delete(f"tse:{uf}")
                if caminho(uf).exists() and '"_simulado"' in caminho(uf).read_text(encoding="utf-8"):
                    caminho(uf).unlink()
            self.stdout.write(self.style.SUCCESS("Simulação apagada."))
            return
        rnd = random.Random(2026)
        for uf, estado in UFS.items():
            secoes = round(rnd.uniform(60, 98), 2)
            cargos = []
            for codigo, nome, _ in cargos_para(uf):
                qtd = 5 if codigo in ("0001", "0003", "0005") else 5
                pesos = sorted((rnd.random() ** 2 for _ in range(qtd)), reverse=True)
                total = sum(pesos)
                base = rnd.randint(800_000, 8_000_000) if codigo in ("0001", "0003", "0005") else rnd.randint(60_000, 300_000)
                cands = []
                for i, p in enumerate(pesos):
                    dig = DIGITOS[codigo]
                    cands.append({
                        "numero": str(rnd.randint(10 ** (dig - 1), 10 ** dig - 1)),
                        "nome": rnd.choice(NOMES), "partido": f"Partido {chr(65 + i)}",
                        "votos": int(base * p / total) if codigo in ("0001", "0003", "0005") else int(base * (1 - i * 0.12)),
                        "percentual": round(100 * p / total, 2),
                        "eleito": codigo in ("0005", "0006") and i == 0 and secoes > 90,
                        "situacao": "Eleito" if codigo in ("0005", "0006") and i == 0 and secoes > 90 else "",
                        "foto": None,
                    })
                cargos.append({"cargo": nome, "secoes_apuradas": secoes, "atualizado": "",
                               "total_candidatos": 412 if codigo in ("0006", "0007", "0008") else qtd,
                               "candidatos": cands})
            cache.set(f"tse:{uf}", {"uf": uf, "estado": estado, "cargos": cargos}, None)
            chaves = {"0001": "pres", "0003": "gov", "0005": "sen", "0006": "depfed", "0007": "depest", "0008": "depest"}
            lista = {"_simulado": {}}
            for (codigo, _, _), k in zip(cargos_para(uf), cargos):
                lista.setdefault(chaves[codigo], {}).update({c["numero"]: [c["nome"], c["partido"]] for c in k["candidatos"]})
            if not caminho(uf).exists() or '"_simulado"' in caminho(uf).read_text(encoding="utf-8"):
                salvar(uf, lista)   # nunca sobrescreve uma lista real baixada do TSE
        self.stdout.write(self.style.SUCCESS("Apuração fictícia criada para os 27 estados."))
"""Worker que atualiza os resultados do TSE em segundo plano.

    python manage.py atualizar_tse            # roda para sempre (produção, via systemd)
    python manage.py atualizar_tse --uma-vez  # roda uma rodada e sai (teste)
"""
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from django.conf import settings
from django.core.management.base import BaseCommand
from apuracao.tse import UFS, atualizar_estado


class Command(BaseCommand):
    help = "Atualiza periodicamente os resultados do TSE no cache"

    def add_arguments(self, parser):
        parser.add_argument("--uma-vez", action="store_true")

    def handle(self, *args, **opts):
        self.parar = False
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "parar", True))
        while not self.parar:
            inicio = time.monotonic()
            # 4 estados em paralelo: rápido, mas educado com o servidor do TSE
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(atualizar_estado, UFS))
            gasto = time.monotonic() - inicio
            self.stdout.write(f"Rodada concluída em {gasto:.1f}s")
            if opts["uma_vez"]:
                break
            espera = max(5, settings.TSE_INTERVALO_SEGUNDOS - gasto)
            while espera > 0 and not self.parar:
                time.sleep(min(1, espera))
                espera -= 1
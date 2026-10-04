import secrets
from functools import lru_cache
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.views.decorators.cache import cache_control, never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from .pix import br_code, qr_svg
from .tse import UFS, resultados
from . import candidatos as cand


@lru_cache(maxsize=1)
def _pix():
    if not (settings.PIX_CHAVE and settings.PIX_NOME and settings.PIX_CIDADE):
        return None
    codigo = br_code(settings.PIX_CHAVE, settings.PIX_NOME, settings.PIX_CIDADE)
    # O SVG é gerado pela biblioteca segno a partir do código Pix (só desenha quadrados;
    # nenhum texto do usuário entra no SVG). Por isso é seguro marcá-lo como HTML confiável.
    return {"codigo": codigo, "qr": mark_safe(qr_svg(codigo))}  # nosec B308 B703


@require_GET
@cache_control(public=True, max_age=60, s_maxage=300)
def index(request):
    return render(request, "index.html", {
        "ufs": sorted(UFS.items(), key=lambda x: x[1]),
        "pix": _pix(),
        "cf_token": settings.CF_ANALYTICS_TOKEN,
        "inicio": settings.APURACAO_INICIO,
        "og_imagem": request.build_absolute_uri("/static/og.jpg"),
        "url_site": request.build_absolute_uri("/"),
    })


@require_GET
@cache_control(public=True, max_age=15, s_maxage=30, stale_while_revalidate=60)
def resultados_uf(request, uf):
    if uf not in UFS:  # a rota só aceita 2 letras minúsculas; aqui garantimos que é um estado real
        raise Http404()
    return JsonResponse(resultados(uf))


@require_GET
def service_worker(request):
    with open(settings.BASE_DIR / "static" / "sw.js", "rb") as f:
        resp = HttpResponse(f.read(), content_type="application/javascript")
    resp["Cache-Control"] = "no-cache"
    return resp


# ---- Contadores simples (sem banco de dados, sem dado pessoal) ----
EVENTOS = {"visita", "estado", "doacao_vista", "doacao_topo", "pix_copiado", "instalou", "compartilhou", "cola_aberta"}


def _incr(chave, expira=None):
    try:
        cache.incr(chave)
    except ValueError:
        cache.add(chave, 0, expira)
        cache.incr(chave)


@csrf_exempt  # não há sessão nem login; o endpoint só soma +1 em contadores fixos
@require_POST
def evento(request, nome):
    if nome in EVENTOS:
        dia = timezone.localdate().isoformat()
        _incr(f"ev:{nome}:total")
        _incr(f"ev:{nome}:{dia}", 60 * 60 * 24 * 60)
    return HttpResponse(status=204)


@never_cache
@require_GET
def painel(request):
    token = request.headers.get("X-Painel-Token") or request.GET.get("t", "")
    if not settings.PAINEL_TOKEN or not secrets.compare_digest(token, settings.PAINEL_TOKEN):
        raise Http404()  # 404 em vez de 403: não revela que o painel existe
    dia = timezone.localdate().isoformat()
    return JsonResponse({
        n: {"hoje": cache.get(f"ev:{n}:{dia}", 0), "total": cache.get(f"ev:{n}:total", 0)}
        for n in sorted(EVENTOS)
    })


@require_GET
@cache_control(public=True, max_age=3600)
def candidatos_uf(request, uf):
    """Lista pública de candidatos do estado. O celular procura o número localmente."""
    if uf not in UFS:
        raise Http404()
    corpo = cand.ler(uf)
    if corpo is None:
        raise Http404()
    return HttpResponse(corpo, content_type="application/json")
"""Cabeçalhos de segurança adicionais em todas as respostas."""
from django.conf import settings

_CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://static.cloudflareinsights.com",
    "style-src 'self' https://fonts.googleapis.com",
    "font-src https://fonts.gstatic.com",
    "img-src 'self' data: https://resultados.tse.jus.br",
    "connect-src 'self' https://cloudflareinsights.com",
    "manifest-src 'self'",
    "worker-src 'self'",
    "base-uri 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
    "object-src 'none'",
])


class CabecalhosSeguranca:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        resp.setdefault("Content-Security-Policy", _CSP)
        resp.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        resp.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.path.startswith("/painel"):
            resp["X-Robots-Tag"] = "noindex, nofollow"
            resp["Cache-Control"] = "no-store"
        return resp
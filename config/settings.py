"""Configurações do projeto. Tudo que muda entre ambientes vem de variáveis de ambiente (.env)."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Lê o arquivo .env automaticamente (sem dependências). Variáveis já definidas no
# ambiente (ex.: systemd em produção) têm prioridade sobre o arquivo.
_env_arquivo = BASE_DIR / ".env"
if _env_arquivo.exists():
    for _linha in _env_arquivo.read_text(encoding="utf-8").splitlines():
        _linha = _linha.strip()
        if _linha and not _linha.startswith("#") and "=" in _linha:
            _k, _v = _linha.split("=", 1)
            _k = _k.strip()
            # Variável vazia no terminal (sobra de um "source .env" antigo) não esconde o valor do arquivo
            if not os.environ.get(_k):
                os.environ[_k] = _v.strip().strip('"').strip("'")


def env(nome, padrao=None):
    return os.environ.get(nome, padrao)


# ---------------------------------------------------------------------------
# Básico e segurança
# ---------------------------------------------------------------------------
# Seguro por padrão: só liga o modo debug se DEBUG=1 estiver explícito.
DEBUG = env("DEBUG", "0") == "1"

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "apenas-para-desenvolvimento-local"
    else:
        # Sem SECRET_KEY definida (ex.: etapa de build da Vercel, que não recebe as variáveis):
        # usa uma chave aleatória temporária. É seguro neste projeto porque ele não tem login,
        # sessão nem nada assinado que precise sobreviver entre reinícios.
        import secrets as _secrets, warnings as _w
        SECRET_KEY = _secrets.token_urlsafe(50)
        _w.warn("SECRET_KEY não definida: usando chave temporária. Defina SECRET_KEY no ambiente.")

ALLOWED_HOSTS = [h.strip() for h in env("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

# Hospedagem na Vercel (a própria Vercel define a variável VERCEL=1)
NA_VERCEL = bool(env("VERCEL"))
if NA_VERCEL:
    ALLOWED_HOSTS.append(".vercel.app")
# Sem worker (Vercel): as páginas buscam no TSE na hora, com cache curto + CDN
BUSCA_SOB_DEMANDA = env("BUSCA_SOB_DEMANDA", "1" if NA_VERCEL else "0") == "1"

INSTALLED_APPS = ["django.contrib.staticfiles", "apuracao"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apuracao.middleware.CabecalhosSeguranca",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": False,
    "OPTIONS": {"context_processors": []},
}]

# Sem banco de dados: o site só exibe dados públicos do TSE.
DATABASES = {}

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = False
USE_TZ = True

# Arquivos estáticos servidos pelo WhiteNoise (com compressão e cache longo)
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = None if NA_VERCEL else BASE_DIR / "staticfiles"
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
WHITENOISE_USE_FINDERS = True        # serve direto de static/, sem precisar de collectstatic
WHITENOISE_MAX_AGE = 3600

# Cabeçalhos de segurança (valem em produção, atrás do Cloudflare com HTTPS)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
# Não há login nem formulários com sessão, mas deixamos os cookies seguros mesmo assim.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Limites contra requisições abusivas
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024  # 10 KB: o site não recebe uploads
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20

# ---------------------------------------------------------------------------
# Cache: Redis em produção; arquivo em disco no desenvolvimento local
# ---------------------------------------------------------------------------
if env("REDIS_URL"):
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "KEY_PREFIX": "apuracao",
    }}
elif NA_VERCEL:
    # Na Vercel o disco é somente leitura: cache em memória de cada instância
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
else:
    CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / ".cache",
    }}

# ---------------------------------------------------------------------------
# TSE
# ---------------------------------------------------------------------------
TSE_BASE_URL = env("TSE_BASE_URL", "https://resultados.tse.jus.br/oficial/ele2026").rstrip("/")
# Proteção: o servidor só pode buscar dados no domínio oficial do TSE.
if not TSE_BASE_URL.startswith("https://resultados.tse.jus.br/"):
    raise ImproperlyConfigured("TSE_BASE_URL precisa começar com https://resultados.tse.jus.br/")
TSE_ELEICAO_FEDERAL = env("TSE_ELEICAO_FEDERAL", "6257")   # 1º turno 2026: Eleição Geral Federal
TSE_ELEICAO_ESTADUAL = env("TSE_ELEICAO_ESTADUAL", "6259")  # 1º turno 2026: Eleições Gerais Estaduais
for _nome in ("TSE_ELEICAO_FEDERAL", "TSE_ELEICAO_ESTADUAL"):
    if not globals()[_nome].isdigit():
        raise ImproperlyConfigured(f"{_nome} deve conter só números")
TSE_INTERVALO_SEGUNDOS = max(30, int(env("TSE_INTERVALO_SEGUNDOS", "60")))

# ---------------------------------------------------------------------------
# Doação via Pix e painel
# ---------------------------------------------------------------------------
PIX_CHAVE = env("PIX_CHAVE", "")
PIX_NOME = env("PIX_NOME", "")
PIX_CIDADE = env("PIX_CIDADE", "")
PAINEL_TOKEN = env("PAINEL_TOKEN", "")
if PAINEL_TOKEN and len(PAINEL_TOKEN) < 32:
    raise ImproperlyConfigured("PAINEL_TOKEN precisa ter pelo menos 32 caracteres")
CF_ANALYTICS_TOKEN = env("CF_ANALYTICS_TOKEN", "")

# ---------------------------------------------------------------------------
# Logs: tudo vai para o journal do systemd (journalctl -u apuracao)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.security.DisallowedHost": {"handlers": [], "propagate": False}},
}

# Início da divulgação dos resultados (horário de Brasília). Antes disso o site mostra a contagem regressiva.
# 2º turno: troque para "2026-10-25T17:00:00-03:00".
from datetime import datetime as _dt
APURACAO_INICIO = env("APURACAO_INICIO", "2026-10-04T17:00:00-03:00")
try:
    _dt.fromisoformat(APURACAO_INICIO)
except ValueError:
    raise ImproperlyConfigured("APURACAO_INICIO deve estar no formato 2026-10-04T17:00:00-03:00")

# ---------------------------------------------------------------------------
# Lista de candidatos (busca do nome na colinha)
# Fonte: DivulgaCandContas do TSE. Confirme o ano e o código da eleição de 2026 com:
#   python manage.py baixar_candidatos --listar-eleicoes
# ---------------------------------------------------------------------------
TSE_CAND_BASE = env("TSE_CAND_BASE", "https://divulgacandcontas.tse.jus.br/divulga/rest/v1").rstrip("/")
if not TSE_CAND_BASE.startswith("https://divulgacandcontas.tse.jus.br/"):
    raise ImproperlyConfigured("TSE_CAND_BASE precisa começar com https://divulgacandcontas.tse.jus.br/")
TSE_CAND_ANO = env("TSE_CAND_ANO", "2026")
TSE_CAND_ELEICAO = env("TSE_CAND_ELEICAO", "")
CANDIDATOS_DIR = BASE_DIR / "dados" / "candidatos"
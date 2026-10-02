from django.urls import path, re_path
from apuracao import views

urlpatterns = [
    path("", views.index, name="index"),
    path("sw.js", views.service_worker),
    re_path(r"^api/evento/(?P<nome>[a-z_]{1,20})/$", views.evento),
    re_path(r"^api/candidatos/(?P<uf>[a-z]{2})/$", views.candidatos_uf),
    re_path(r"^api/(?P<uf>[a-z]{2})/$", views.resultados_uf),
    path("painel/", views.painel),
]
# Qualquer outra URL cai no 404 padrão do Django (sem páginas de debug em produção).
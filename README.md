# Apuração 2026 por estado

Site mobile-first que mostra a apuração oficial do TSE filtrada por estado:
presidente, governador, senador, deputado federal e deputado estadual (distrital no DF),
sempre com os 5 mais votados de cada cargo.

- Sem banco de dados e sem coleta de dados pessoais (o nome fica só no celular do eleitor).
- Instalável na tela inicial do celular (PWA).
- Doação opcional via Pix com QR Code.
- Contadores anônimos de uso em `/painel/`.

## Documentação
- **INSTALACAO.md**: rodar o projeto no seu computador, passo a passo.
- **DEPLOY.md**: colocar no ar com segurança e performance, passo a passo.

## Como funciona

    Eleitor → Cloudflare (cache 30s) → Nginx → Gunicorn/Django ──lê──→ Redis
                                                                      ↑ grava
                                       worker "atualizar_tse" ──1x/min──→ TSE

O site NUNCA chama o TSE durante uma visita. Um processo separado (worker) busca os dados
de todos os estados a cada minuto e grava no Redis. As páginas só leem do Redis.
Por isso o site aguenta picos de acesso e continua de pé mesmo se o TSE ficar lento.

## Estrutura

    apuracao/tse.py              busca e limpa os dados do TSE
    apuracao/management/commands/atualizar_tse.py   o worker
    apuracao/views.py            rotas: página, API por estado, contadores, painel
    apuracao/pix.py              gera o QR Code e o "copia e cola" do Pix
    apuracao/middleware.py       cabeçalhos de segurança (CSP etc.)
    config/settings.py           configurações (tudo vem do .env)
    templates/index.html         a página
    static/app.js, app.css       frontend
    static/sw.js, manifest       atalho na tela inicial

# Deploy em produção — passo a passo

Guia para colocar o site no ar com **segurança** e **performance**, gastando pouco.
Siga na ordem. Cada comando tem uma explicação do que faz.

> Convenção: troque `seudominio.com.br` pelo seu domínio e `IP_DO_SERVIDOR` pelo IP do VPS.

---

## 0. Visão geral

    Eleitor ──HTTPS──> Cloudflare ──HTTPS──> Nginx (VPS) ──> Gunicorn/Django ──> Redis
                       │ cache, WAF,                                               ↑
                       │ anti-DDoS                   worker atualizar_tse ─1x/min──┘──> TSE

Camadas de proteção, de fora para dentro:

1. **Cloudflare**: esconde o IP real do servidor, absorve ataques e responde do cache.
2. **Firewall (UFW)**: o servidor só aceita HTTP/HTTPS vindo do Cloudflare. Ninguém acessa direto.
3. **Nginx**: limita requisições por pessoa, bloqueia arquivos sensíveis, esconde a versão.
4. **Django**: sem banco, sem login, sem upload; só aceita os estados válidos; cabeçalhos
   de segurança (CSP, HSTS); recusa domínios que não são o seu.
5. **Sistema**: SSH só com chave, sem root, atualizações de segurança automáticas, fail2ban,
   serviços rodando com usuário sem privilégios.

## 1. Custos

| Item | Onde | Custo aproximado |
|---|---|---|
| Domínio .com.br | registro.br | ~R$ 40/ano |
| VPS 2 vCPU / 8 GB / Ubuntu 24.04, datacenter no Brasil | Hostinger KVM 2 ou Magalu Cloud | ~R$ 40–70/mês |
| CDN, HTTPS, DNS, WAF, analytics | Cloudflare Free | R$ 0 |
| Redis | no próprio VPS | R$ 0 |

Contrate o VPS mensal (não anual) e cancele depois do 2º turno se não fizer mais sentido.

---

## 2. Domínio e Cloudflare (faça HOJE: a propagação demora)

1. Registre o domínio em **https://registro.br** (é o órgão oficial do .com.br).
   - Evite nomes com "tse", "oficial", "gov", "eleitoral".
2. Crie conta grátis em **https://dash.cloudflare.com** → "Add a site" → plano **Free**.
3. O Cloudflare mostra **2 nameservers** (ex.: `ana.ns.cloudflare.com`).
4. No registro.br: seu domínio → **DNS** → "Alterar servidores DNS" → cole os 2 nameservers.
5. Aguarde o e-mail do Cloudflare dizendo que o site está ativo (minutos a algumas horas).
6. No Cloudflare, ative **2FA** na sua conta (My Profile → Authentication).
   Faça o mesmo no registro.br e no painel do VPS. Conta invadida = site invadido.

---

## 3. Primeiro acesso ao servidor e proteção do SSH

### 3.1 Crie uma chave SSH no SEU computador (se ainda não tiver)
```bash
ssh-keygen -t ed25519 -C "deploy-apuracao"
# aperte Enter para o local padrão e defina uma senha para a chave
cat ~/.ssh/id_ed25519.pub     # copie essa linha
```
No painel do VPS, cadastre essa chave pública ao criar o servidor (Ubuntu 24.04).

### 3.2 Entre e crie seu usuário (nunca trabalhe como root)
```bash
ssh root@IP_DO_SERVIDOR
adduser danilo                      # crie uma senha forte
usermod -aG sudo danilo
mkdir -p /home/danilo/.ssh
cp ~/.ssh/authorized_keys /home/danilo/.ssh/
chown -R danilo:danilo /home/danilo/.ssh && chmod 700 /home/danilo/.ssh && chmod 600 /home/danilo/.ssh/authorized_keys
```

### 3.3 Em OUTRO terminal, teste o login com o novo usuário ANTES de continuar
```bash
ssh danilo@IP_DO_SERVIDOR
sudo whoami          # deve responder: root
```

### 3.4 Desligue login por senha e login como root
```bash
sudo tee /etc/ssh/sshd_config.d/99-seguranca.conf > /dev/null <<'CONF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
X11Forwarding no
CONF
sudo sshd -t && sudo systemctl restart ssh
```
Mantenha a sessão atual aberta e teste de novo em outro terminal. Se travar, use o
console web do painel do VPS para corrigir.

### 3.5 Atualizações automáticas de segurança e fail2ban
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y unattended-upgrades fail2ban
sudo dpkg-reconfigure -plow unattended-upgrades     # responda "Yes"
sudo systemctl enable --now fail2ban                # bloqueia IPs que erram o SSH várias vezes
sudo timedatectl set-timezone America/Sao_Paulo
```

---

## 4. Firewall: só o Cloudflare entra pela porta 80/443

Assim, mesmo que alguém descubra o IP do servidor, não consegue acessar o site por fora
do Cloudflare (e não escapa do cache, do WAF e do anti-DDoS).

```bash
sudo apt install -y ufw curl
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH

for ip in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do
  sudo ufw allow proto tcp from "$ip" to any port 80,443 comment 'cloudflare'
done

sudo ufw --force enable
sudo ufw status numbered
```

---

## 5. Instalar o software

```bash
sudo apt install -y python3-venv python3-pip nginx redis-server unzip
```

### 5.1 Redis: só local, sem disco, com limite de memória
```bash
sudo sed -i 's/^#\? *bind .*/bind 127.0.0.1 -::1/' /etc/redis/redis.conf
sudo sed -i 's/^#\? *protected-mode .*/protected-mode yes/' /etc/redis/redis.conf
sudo sed -i 's/^save .*/# save desativado/' /etc/redis/redis.conf
echo 'save ""'                        | sudo tee -a /etc/redis/redis.conf
echo 'maxmemory 512mb'                | sudo tee -a /etc/redis/redis.conf
echo 'maxmemory-policy allkeys-lru'   | sudo tee -a /etc/redis/redis.conf
sudo systemctl restart redis-server
redis-cli ping      # deve responder PONG
```
O Redis guarda só cache e contadores; não precisa salvar em disco.

### 5.2 Usuário do sistema e código
O app roda com um usuário próprio, sem senha e sem shell. Se alguém explorar o app,
não ganha acesso ao resto do servidor.

```bash
sudo adduser --system --group --home /srv/apuracao --shell /usr/sbin/nologin apuracao
```
No SEU computador, envie o zip:
```bash
scp apuracao2026.zip danilo@IP_DO_SERVIDOR:/tmp/
```
No servidor:
```bash
sudo unzip -o /tmp/apuracao2026.zip -d /srv/apuracao
sudo chown -R apuracao:apuracao /srv/apuracao
cd /srv/apuracao/apuracao2026
sudo -u apuracao python3 -m venv .venv
sudo -u apuracao .venv/bin/pip install --upgrade pip
sudo -u apuracao .venv/bin/pip install -r requirements.txt
```

### 5.3 Arquivo .env de produção
```bash
sudo -u apuracao cp .env.exemplo .env
sudo -u apuracao .venv/bin/python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(50))"
sudo -u apuracao .venv/bin/python -c "import secrets; print('PAINEL_TOKEN=' + secrets.token_urlsafe(32))"
sudo nano .env
```
Preencha:
```
DEBUG=0
SECRET_KEY=(o gerado acima)
ALLOWED_HOSTS=seudominio.com.br,www.seudominio.com.br
REDIS_URL=redis://127.0.0.1:6379/1
TSE_BASE_URL=https://resultados.tse.jus.br/oficial/ele2026
TSE_ELEICAO_FEDERAL=(código confirmado, ver INSTALACAO.md seção 8)
TSE_ELEICAO_ESTADUAL=(código confirmado)
TSE_INTERVALO_SEGUNDOS=60
PIX_CHAVE=(chave Pix da conta MEI)
PIX_NOME=(nome da empresa, sem acento, até 25 letras)
PIX_CIDADE=SALVADOR
PAINEL_TOKEN=(o gerado acima)
CF_ANALYTICS_TOKEN=(preencha depois, passo 8)
```
Proteja o arquivo (só o usuário do app lê):
```bash
sudo chown apuracao:apuracao .env && sudo chmod 600 .env
```
Guarde o SECRET_KEY e o PAINEL_TOKEN num gerenciador de senhas. Nunca mande por WhatsApp
nem suba para o GitHub.

### 5.4 Verificar e preparar os arquivos estáticos
```bash
sudo -u apuracao bash -c 'set -a; . ./.env; set +a; .venv/bin/python manage.py check --deploy'
sudo -u apuracao bash -c 'set -a; . ./.env; set +a; .venv/bin/python manage.py collectstatic --noinput'
```
O `check --deploy` vai mostrar 2 avisos esperados:
- **W003 (CSRF)**: o site não tem login, sessão nem formulário que altere dados. O único
  POST é o contador anônimo, que só soma +1 em nomes fixos.
- **W021 (HSTS preload)**: desligado de propósito; só ligue se tiver certeza de que o
  domínio e todos os subdomínios terão HTTPS para sempre.

---

## 6. Serviços (systemd)

### 6.1 Site (Gunicorn)
```bash
sudo tee /etc/systemd/system/apuracao.service > /dev/null <<'CONF'
[Unit]
Description=Apuracao 2026 - site
After=network.target redis-server.service
Requires=redis-server.service

[Service]
User=apuracao
Group=apuracao
WorkingDirectory=/srv/apuracao/apuracao2026
EnvironmentFile=/srv/apuracao/apuracao2026/.env
ExecStart=/srv/apuracao/apuracao2026/.venv/bin/gunicorn config.wsgi \
  --bind 127.0.0.1:8000 \
  --workers 3 --threads 4 --worker-class gthread \
  --timeout 30 --graceful-timeout 20 \
  --max-requests 5000 --max-requests-jitter 500 \
  --limit-request-line 2048 --limit-request-fields 50 \
  --access-logfile -
Restart=always
RestartSec=3

# Endurecimento: o processo não pode virar root nem escrever fora do necessário
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/apuracao/apuracao2026
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
CONF
```
Regra dos workers: `2 × núcleos + 1`. Com 2 vCPUs, 3 a 5 está bom. Com o Cloudflare
na frente e tudo vindo do Redis, isso aguenta muito tráfego.

### 6.2 Worker do TSE
```bash
sudo tee /etc/systemd/system/apuracao-worker.service > /dev/null <<'CONF'
[Unit]
Description=Apuracao 2026 - worker do TSE
After=network-online.target redis-server.service
Wants=network-online.target
Requires=redis-server.service

[Service]
User=apuracao
Group=apuracao
WorkingDirectory=/srv/apuracao/apuracao2026
EnvironmentFile=/srv/apuracao/apuracao2026/.env
ExecStart=/srv/apuracao/apuracao2026/.venv/bin/python manage.py atualizar_tse
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/apuracao/apuracao2026

[Install]
WantedBy=multi-user.target
CONF
```

### 6.3 Ligar
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now apuracao apuracao-worker
sudo systemctl status apuracao apuracao-worker --no-pager
curl -s http://127.0.0.1:8000/api/ba/ -H "Host: seudominio.com.br" | head -c 300
```

---

## 7. Nginx

### 7.1 Certificado de origem do Cloudflare (grátis, válido por 15 anos)
No Cloudflare: **SSL/TLS → Origin Server → Create Certificate** (deixe o padrão).
Copie os dois blocos:
```bash
sudo mkdir -p /etc/ssl/cloudflare && sudo chmod 700 /etc/ssl/cloudflare
sudo nano /etc/ssl/cloudflare/origin.pem    # cole o "Origin Certificate"
sudo nano /etc/ssl/cloudflare/origin.key    # cole a "Private Key"
sudo chmod 600 /etc/ssl/cloudflare/*
```

### 7.2 IP real do visitante (sem isso o limite de requisições não funciona)
Atrás do Cloudflare, todo mundo chegaria com o IP do Cloudflare. Isto restaura o IP real:
```bash
{
  for ip in $(curl -s https://www.cloudflare.com/ips-v4) $(curl -s https://www.cloudflare.com/ips-v6); do
    echo "set_real_ip_from $ip;"
  done
  echo "real_ip_header CF-Connecting-IP;"
} | sudo tee /etc/nginx/conf.d/cloudflare-realip.conf
```

### 7.3 Configurações globais
```bash
sudo tee /etc/nginx/conf.d/apuracao-global.conf > /dev/null <<'CONF'
server_tokens off;                      # não mostra a versão do Nginx
client_max_body_size 10k;               # o site não recebe uploads
client_body_timeout 10s;
client_header_timeout 10s;
keepalive_timeout 30s;
send_timeout 15s;

# Limites por IP real do visitante
limit_req_zone $binary_remote_addr zone=api:10m    rate=10r/s;
limit_req_zone $binary_remote_addr zone=evento:10m rate=1r/s;
limit_conn_zone $binary_remote_addr zone=conexoes:10m;
limit_req_status 429;
limit_conn_status 429;

gzip on;
gzip_types application/json application/javascript text/css image/svg+xml;
gzip_min_length 1024;
CONF
```

### 7.4 O site
```bash
sudo tee /etc/nginx/sites-available/apuracao > /dev/null <<'CONF'
# Qualquer acesso que não seja pelo seu domínio é descartado
server {
    listen 80 default_server;
    listen 443 ssl default_server;
    ssl_certificate     /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin.key;
    return 444;
}

server {
    listen 80;
    server_name seudominio.com.br www.seudominio.com.br;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name seudominio.com.br www.seudominio.com.br;

    ssl_certificate     /etc/ssl/cloudflare/origin.pem;
    ssl_certificate_key /etc/ssl/cloudflare/origin.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    limit_conn conexoes 20;

    # Só métodos que o site usa
    if ($request_method !~ ^(GET|HEAD|POST)$) { return 405; }

    # Nada de arquivos ocultos (.env, .git...) nem extensões perigosas
    location ~ /\.            { deny all; return 404; }
    location ~* \.(py|pyc|env|sh|sql|bak|log|ini|conf)$ { deny all; return 404; }

    location /static/ {
        alias /srv/apuracao/apuracao2026/staticfiles/;
        expires 7d;
        add_header Cache-Control "public";
        access_log off;
    }

    location /api/evento/ {
        limit_req zone=evento burst=10 nodelay;
        proxy_pass http://127.0.0.1:8000;
        include /etc/nginx/apuracao-proxy.conf;
    }

    location / {
        limit_req zone=api burst=30 nodelay;
        proxy_pass http://127.0.0.1:8000;
        include /etc/nginx/apuracao-proxy.conf;
    }
}
CONF

sudo tee /etc/nginx/apuracao-proxy.conf > /dev/null <<'CONF'
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto https;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_connect_timeout 5s;
proxy_read_timeout 30s;
proxy_hide_header X-Powered-By;
CONF

sudo ln -sf /etc/nginx/sites-available/apuracao /etc/nginx/sites-enabled/apuracao
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## 8. Cloudflare: configurações

**DNS**
- Registro `A` → nome `@` → `IP_DO_SERVIDOR` → **Proxied** (nuvem laranja).
- Registro `A` → nome `www` → `IP_DO_SERVIDOR` → **Proxied**.
- Nunca deixe a nuvem cinza: isso expõe o IP real.

**SSL/TLS**
- Modo: **Full (strict)**.
- Edge Certificates: **Always Use HTTPS** ligado, **Minimum TLS 1.2**, **Automatic HTTPS Rewrites** ligado.

**Caching → Cache Rules** (crie nesta ordem)
1. Nome "API resultados": *URI Path* matches regex `^/api/[a-z]{2}/$` → **Eligible for cache**,
   Edge TTL = **Use cache-control header if present** (o app envia 30s).
2. Nome "Estáticos": *URI Path* starts with `/static/` → **Eligible for cache**, Edge TTL 1 dia.
3. Nome "Nunca cachear": *URI Path* starts with `/painel` OR starts with `/api/evento/` → **Bypass cache**.

Com isso, se 10 mil pessoas abrirem a Bahia no mesmo minuto, o servidor recebe cerca de
2 requisições por minuto para a Bahia. O resto o Cloudflare responde.

**Security**
- Security → Settings: **Bot Fight Mode** ligado; Security Level **Medium**.
- Security → WAF → Rate limiting rules (o plano Free permite 1 regra):
  *URI Path* starts with `/api/` → mais de **100 requisições em 10 segundos** por IP →
  **Block** por 10 segundos.
- Security → WAF → Custom rules (Free permite 5): bloqueie caminhos de varredura comuns:
  *URI Path* contains `wp-` OR contains `.php` OR contains `/.git` OR contains `.env` → **Block**.

**Analytics**
- Analytics & Logs → Web Analytics → adicione o site → copie o token para
  `CF_ANALYTICS_TOKEN` no `.env` → `sudo systemctl restart apuracao`.

---

## 9. Checklist final (faça tudo antes de domingo)

Funcionamento
- [ ] `https://seudominio.com.br` abre com cadeado.
- [ ] `https://www.seudominio.com.br` também abre.
- [ ] Ao escolher um estado, aparecem os dados (com os códigos reais do TSE).
- [ ] Atalho testado em um Android (Chrome) e em um iPhone (Safari).
- [ ] Pix de R$ 1 feito por outro celular caiu na conta MEI certa.
- [ ] `https://seudominio.com.br/painel/?t=SEU_TOKEN` mostra os contadores.

Segurança (todos devem FALHAR, é isso que você quer)
- [ ] `curl -k https://IP_DO_SERVIDOR` do seu computador → sem resposta (firewall).
- [ ] `https://seudominio.com.br/.env` → 404.
- [ ] `https://seudominio.com.br/painel/` sem token → 404.
- [ ] `https://seudominio.com.br/api/xx/` → 404.
- [ ] `ssh root@IP_DO_SERVIDOR` → recusado.
- [ ] https://securityheaders.com com seu domínio → nota A.
- [ ] https://www.ssllabs.com/ssltest com seu domínio → nota A.

Performance
- [ ] Teste de carga do seu computador (instale `apache2-utils`):
      `ab -n 3000 -c 100 https://seudominio.com.br/api/ba/` → sem erros.
- [ ] No segundo acesso a `/api/ba/`, o cabeçalho `cf-cache-status` mostra `HIT`:
      `curl -sI https://seudominio.com.br/api/ba/ | grep -i cf-cache`

---

## 10. No dia da eleição

```bash
journalctl -u apuracao-worker -f        # deve mostrar "Rodada concluída" a cada minuto
journalctl -u apuracao -f               # acessos ao site
htop                                    # uso de CPU e memória
sudo tail -f /var/log/nginx/error.log   # erros e limites atingidos
```

Se o TSE mudar algo e os dados pararem:
1. Veja o erro no log do worker.
2. Corrija o `.env` ou o `apuracao/tse.py`.
3. `sudo systemctl restart apuracao-worker`.
O site continua mostrando o último resultado bom enquanto você corrige.

Se o servidor ficar lento: aumente `--workers` no serviço, rode
`sudo systemctl daemon-reload && sudo systemctl restart apuracao`, ou faça upgrade do
plano do VPS pelo painel (costuma levar poucos minutos).

## 11. Atualizar o código depois

```bash
scp apuracao2026.zip danilo@IP_DO_SERVIDOR:/tmp/
ssh danilo@IP_DO_SERVIDOR
cd /srv/apuracao
sudo cp apuracao2026/.env /tmp/env.bkp
sudo unzip -o /tmp/apuracao2026.zip -d /srv/apuracao
sudo cp /tmp/env.bkp apuracao2026/.env && sudo rm /tmp/env.bkp
sudo chown -R apuracao:apuracao /srv/apuracao && sudo chmod 600 apuracao2026/.env
cd apuracao2026
sudo -u apuracao .venv/bin/pip install -r requirements.txt
sudo -u apuracao bash -c 'set -a; . ./.env; set +a; .venv/bin/python manage.py collectstatic --noinput'
sudo systemctl restart apuracao apuracao-worker
```
Depois de mudar arquivos em `static/`, troque `apuracao-v2` em `static/sw.js` para
`apuracao-v3` (e assim por diante) para os celulares baixarem a versão nova. No
Cloudflare, use **Caching → Purge Everything**.

## 12. Depois do 2º turno

- Desative os serviços ou cancele o VPS.
- Se for manter o domínio, deixe uma página simples agradecendo.
- O Redis não guarda nada em disco, então não sobra dado nenhum no servidor.

## 13. Horário da apuração e 2º turno

O site mostra uma contagem regressiva até `APURACAO_INICIO` (padrão: 4/10/2026 às 17h de
Brasília). Depois desse horário, mostra "A apuração começou" até o TSE publicar os
primeiros números, e então troca sozinho para os resultados.

Para o 2º turno (25/10), no `.env`:
```
APURACAO_INICIO=2026-10-25T17:00:00-03:00
TSE_ELEICAO_FEDERAL=(código do 2º turno, ver INSTALACAO.md seção 8)
TSE_ELEICAO_ESTADUAL=(código do 2º turno)
```
Depois: `sudo systemctl restart apuracao apuracao-worker` e, no Cloudflare, Purge Everything.

## 14. Monitoramento gratuito

Crie uma conta em https://uptimerobot.com (plano Free), adicione um monitor HTTP(s) para
`https://seudominio.com.br/api/ba/` a cada 5 minutos e ative o alerta pelo app no celular.
Se o site cair, você recebe uma notificação na hora.

## 15. Testar a prévia do link

Cole o endereço do site em https://developers.facebook.com/tools/debug/ (vale para
WhatsApp e Instagram também) e clique em "Scrape Again" depois de cada mudança na imagem.

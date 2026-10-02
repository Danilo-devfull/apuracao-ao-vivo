# Instalação local (no seu computador)

Objetivo: rodar o site no seu computador para testar antes de subir para o servidor.
Tempo estimado: 15 minutos.

## 1. Pré-requisitos

- **Python 3.11 ou mais novo.** Confira com `python3 --version`.
  - Windows: instale pelo python.org e marque "Add Python to PATH".
- **Git** (opcional, para versionar).
- Não precisa de Redis no computador: em modo local o cache usa uma pasta `.cache/`.

## 2. Descompactar e entrar na pasta

```bash
unzip apuracao2026.zip
cd apuracao2026
```

## 3. Criar o ambiente virtual

O ambiente virtual isola as bibliotecas deste projeto das outras do seu computador.

Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Quando ativo, o terminal mostra `(.venv)` no começo da linha.
Toda vez que abrir um terminal novo, ative de novo.

## 4. Instalar as dependências

```bash
pip install -r requirements.txt
```

## 5. Criar o arquivo .env

```bash
cp .env.exemplo .env        # Windows: copy .env.exemplo .env
```

Abra o `.env` e, para rodar localmente, deixe assim:

```
DEBUG=1
SECRET_KEY=
ALLOWED_HOSTS=localhost,127.0.0.1
REDIS_URL=
TSE_BASE_URL=https://resultados.tse.jus.br/oficial/ele2026
TSE_ELEICAO_FEDERAL=0
TSE_ELEICAO_ESTADUAL=0
PIX_CHAVE=sua-chave-pix
PIX_NOME=NOME DA EMPRESA
PIX_CIDADE=SALVADOR
PAINEL_TOKEN=
```

Com `DEBUG=1` o SECRET_KEY pode ficar vazio. Em produção, NUNCA use DEBUG=1.

O Django não lê o `.env` sozinho. Carregue as variáveis no terminal:

Linux / macOS:
```bash
set -a; source .env; set +a
```

Windows (PowerShell):
```powershell
Get-Content .env | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
  $n, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($n.Trim(), $v.Trim())
}
```

## 6. Verificar e rodar

```bash
python manage.py check          # deve dizer "System check identified no issues"
python manage.py runserver
```

Abra http://127.0.0.1:8000. Escolha um estado: vai aparecer "Resultados ainda não
divulgados pelo TSE", porque o worker ainda não rodou. Isso é esperado.

## 7. Rodar o worker (em outro terminal)

Abra um segundo terminal, entre na pasta, ative o `.venv`, carregue o `.env` e rode:

```bash
python manage.py atualizar_tse --uma-vez
```

- Com códigos de eleição `0`, ele vai registrar avisos de "TSE indisponível". Normal.
- Quando você tiver os códigos reais (próxima seção), os dados aparecem no site.
- Sem `--uma-vez`, ele fica rodando e atualiza a cada minuto (como em produção).

## 8. Descobrir os códigos da eleição de 2026

O TSE só publica isso perto do dia. No sábado ou domingo cedo:

1. Abra https://resultados.tse.jus.br no Chrome do computador.
2. Aperte F12, vá na aba **Network/Rede** e filtre por `json`.
3. Navegue até um resultado (ex.: Presidente, Bahia).
4. Procure um arquivo terminado em `-r.json`, por exemplo:
   `.../ele2026/619/dados-simplificados/ba/ba-c0001-e000619-r.json`
   - `ele2026` → confirma o `TSE_BASE_URL`
   - `619` → é o código da eleição. Use o de Presidente em `TSE_ELEICAO_FEDERAL`.
5. Repita com Governador da Bahia e use o código em `TSE_ELEICAO_ESTADUAL`.
   (Em 2022 eram diferentes: 544 federal e 546 estadual.)
6. Abra um desses `.json` e confira se existem os campos `cand`, `nm`, `vap`, `pvap`, `pst`.
   Se os nomes mudaram, ajuste a função `_normalizar` em `apuracao/tse.py`.

Teste com os códigos de 2022 para ver o site funcionando agora (se o TSE ainda mantiver esses arquivos; se der erro 403/404, eles foram retirados e você só conseguirá testar com os de 2026):
```
TSE_BASE_URL=https://resultados.tse.jus.br/oficial/ele2022
TSE_ELEICAO_FEDERAL=544
TSE_ELEICAO_ESTADUAL=546
```
Recarregue o `.env`, rode `python manage.py atualizar_tse --uma-vez` e atualize o site.

## 9. Testar no celular

Com o computador e o celular no mesmo Wi-Fi:
```bash
python manage.py runserver 0.0.0.0:8000
```
Coloque o IP do computador no `ALLOWED_HOSTS` (ex.: `192.168.0.10`) e acesse
`http://192.168.0.10:8000` no celular. O botão de "Adicionar à tela inicial" só aparece
com HTTPS, então ele só funciona de verdade no servidor.

## 10. Testar o painel

Coloque no `.env` um `PAINEL_TOKEN` com 32+ caracteres:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```
Acesse `http://127.0.0.1:8000/painel/?t=SEU_TOKEN`. Sem o token certo, a página dá 404.

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `ImproperlyConfigured: Defina SECRET_KEY` | `DEBUG` não está `1` ou o `.env` não foi carregado |
| Erro 400 "Bad Request" | O endereço que você usou não está no `ALLOWED_HOSTS` |
| "Resultados ainda não divulgados" | Worker não rodou ou códigos de eleição errados |
| `command not found: python` | Use `python3`, ou o `.venv` não está ativo |

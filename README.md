# Controle de Vencimentos — Segurança do Trabalho

Aplicação web (Streamlit + SQLAlchemy + SQLite) para controlar vencimentos de
treinamentos, exames (ASO), equipamentos, documentos, contratos, certificados e
obrigações de SST, com multiempresa, perfis de acesso, auditoria e anexos.

Desenvolvido por **[NOLTH Web Design Studio](https://nolth.netlify.app/)** — Camilla Fialho.

**Destaques:** painel de vencimentos com gráficos · perfil completo do colaborador
(ASOs, treinamentos, anexos e histórico de renovações) · turmas de treinamento por NR ·
consulta de CNPJ em dados públicos · CPF mascarado com auditoria (LGPD) ·
relatórios em Excel · tema claro e escuro · 63 testes automatizados (Pytest).

**Executar no Windows:** dê dois cliques em `ABRIR_SISTEMA.bat` (após a instalação abaixo).

---

## 1. Requisitos

- **Python 3.12 ou superior** (testado com 3.12/3.13)
- Acesso à internet **na instalação** (para baixar as dependências)
- Windows, Linux ou macOS

## 2. Instalação

```bash
# 1) entre na pasta do projeto
cd controle_vencimentos_sst

# 2) crie e ative um ambiente virtual
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3) instale as dependências
pip install -r requirements.txt

# 4) (opcional) configure variáveis
copy .env.example .env        # Windows
cp .env.example .env          # Linux/macOS
```

## 3. Criar o banco e a primeira empresa

```bash
python scripts/inicializar.py
```

O script cria `data/sst.db`, pergunta o nome da empresa, o e-mail e a senha do
administrador e carrega um **catálogo sugerido de ~27 tipos de controle**
(NR-35, NR-10, NR-33, ASO, extintores, PGR, PCMSO, AVCB…). As periodicidades
são sugestões: revise em **Tipos de controle**.

Modo não interativo:

```bash
python scripts/inicializar.py --empresa "Minha Empresa" --cnpj 11222333000181 \
  --nome "Administrador" --email admin@empresa.com.br --senha "SenhaForte2026"
```

### Dados de demonstração (opcional)

```bash
python scripts/dados_demo.py
```

Cria a empresa **"Empresa Demonstração"** com 2 unidades, 20 colaboradores,
8 extintores, documentos e a matriz de exigências por cargo.
Login: `demo@exemplo.com.br` / `Demo2026senha`.

## 4. Executar

```bash
streamlit run app.py
```

Abra http://localhost:8501 no navegador.

## 5. Testar

```bash
pip install pytest
python -m pytest -v
```

| Suíte | O que verifica |
|---|---|
| `tests/domain` | cálculo de datas (meses com 28/29/30/31 dias), status nos limites da antecedência, CPF, CNPJ numérico e **alfanumérico**, política e hash de senha, permissões |
| `tests/infra` | exportação Excel com proteção contra injeção de fórmula; anexos (assinatura do arquivo, path traversal, detecção de adulteração) |
| `tests/services` | banco real temporário: chaves estrangeiras ativas, CRUD completo com lixeira, **isolamento entre empresas**, escopo por unidade, cálculo e ajuste de vencimento, renovação com histórico, cancelamento que reativa o anterior, lote, ocultação do resultado de ASO, anexos, pendências, login com bloqueio, usuários |

### Roteiro de teste manual (≈10 min)

1. `python scripts/dados_demo.py` e `streamlit run app.py`; entre com o login demo.
2. **Painel**: confira indicadores, gráficos e a tabela "Ação imediata"; filtre por unidade.
3. **Vencimentos** → selecione uma linha vencida → aba **Ações → Renovar** → informe
   a nova data de emissão e salve. Abra **Histórico**: os dois registros aparecem.
4. Na aba **Anexos**, envie um PDF; tente enviar um `.txt` renomeado para `.pdf` (deve ser recusado).
5. **Novo lançamento** do mesmo tipo para o mesmo colaborador: o sistema bloqueia e indica "Renovar".
6. Informe uma data de vencimento diferente da calculada sem justificativa: erro de validação.
7. **Pendências**: veja colaboradores sem registro; lance pelo **Lançamento em lote** e volte.
8. **Usuários** → crie um "Técnico SST" restrito a uma unidade. Saia e entre com ele (senha temporária):
   ele troca a senha, só vê a sua unidade e não vê o resultado do ASO.
9. Erre a senha 5 vezes: a conta é bloqueada por 15 minutos.
10. **Auditoria**: todas as ações anteriores estão registradas.

## 6. Estrutura

```
app.py                      entrada Streamlit (login + navegação lateral por perfil)
scripts/                    inicializar.py, dados_demo.py
src/sst/
  config.py                 configuração por .env
  logging_config.py         logs rotativos em logs/app.log
  domain/                   regras puras: enums, status, datas, validadores, permissões, exceções
  schemas/                  validação de entrada (Pydantic) com mensagens em pt-BR
  infra/
    db/                     engine (PRAGMAs do SQLite), base, models
    repositories/           repositório com filtro obrigatório de empresa
    armazenamento.py        anexos seguros em disco
    excel/                  exportação Excel
    seguranca.py            hash de senha (scrypt)
    seed_catalogo.py        catálogo sugerido de NRs
  services/                 regras de negócio, permissões e auditoria (sem Streamlit)
  ui/                       componentes, gráficos, página CRUD genérica e páginas
tests/
data/  logs/                gerados em execução (fora do git)
```

## 7. Configuração (`.env`)

| Variável | Padrão | Descrição |
|---|---|---|
| `SST_DATABASE_URL` | `sqlite:///data/sst.db` | URL SQLAlchemy |
| `SST_ANEXOS_DIR` | `data/anexos` | Pasta dos anexos |
| `SST_LOG_DIR` / `SST_LOG_LEVEL` | `logs` / `INFO` | Logs |
| `SST_TIMEZONE` | `America/Sao_Paulo` | Fuso para o "hoje" dos status |
| `SST_SESSAO_TIMEOUT_MIN` | `30` | Expiração por inatividade |
| `SST_LOGIN_MAX_TENTATIVAS` / `SST_LOGIN_BLOQUEIO_MIN` | `5` / `15` | Bloqueio de login |
| `SST_ANEXO_MAX_MB` | `10` | Tamanho máximo de anexo (ajuste também `.streamlit/config.toml`) |

## 8. Backup

Com a aplicação parada, copie `data/sst.db` e a pasta `data/anexos/`.
Com a aplicação rodando (modo WAL), use:

```bash
sqlite3 data/sst.db ".backup data/backup_$(date +%Y%m%d).db"
```

## 9. Produção

- Publique atrás de um proxy reverso com **HTTPS** (Nginx, Caddy, IIS).
- Não use hospedagem pública compartilhada para dados de saúde (LGPD).
- Restrinja permissões das pastas `data/` e `logs/` ao usuário do serviço.
- SQLite atende bem até cerca de 10 usuários gravando ao mesmo tempo; acima disso,
  migre para PostgreSQL alterando `SST_DATABASE_URL` (os models já são portáveis).

## 10. Decisões de implementação

- **E-mail único em toda a plataforma** (não por empresa), para o login não precisar
  de "código da empresa". Uma pessoa em duas empresas usa dois e-mails.
- **Hash de senha com `hashlib.scrypt`** (biblioteca padrão), sem dependência extra.
- **Tabelas criadas com `create_all`** nesta versão; a adoção do Alembic para migrações
  está prevista antes da primeira atualização de schema em cliente.
- **Técnico SST não vê o resultado do ASO** por padrão (LGPD). Ajustável em
  `src/sst/domain/permissoes.py`.
- **Status nunca é gravado**: é sempre calculado a partir da data de vencimento.
- **Renovar** cria um novo registro e preserva o anterior; cancelar uma renovação
  reativa o registro anterior.

## 11. Próximas fases (plano aprovado)

Importação de planilhas Excel com pré-validação · relatórios PDF (ReportLab) ·
alertas por e-mail (worker agendado) · backup pela interface · Alembic.

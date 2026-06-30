# REDOPS — Red Team Exercise Management Platform

<p align="center">
  <img src="docs/screenshots/dashboard.png" alt="REDOPS Dashboard" width="900">
</p>

> Plataforma interna para gerenciamento de exercícios Red Team. Inspirada visualmente no HackTheBox e TryHackMe, com arquitetura baseada em *Architecture Patterns with Python* (DDD, Repository Pattern, Unit of Work, Service Layer).

---

## Funcionalidades

- **Wizard de configuração** guiado em 5 passos: exercício → operadores → Blue Teams → cenários → atribuições
- **Cenários reutilizáveis** com máquinas alvo e linhas de controle IT/OT
- **Dashboard público** em tempo real (polling 5s) com progresso IT+OT por Blue Team
- **Área do operador** com registro de ataques e toggle de linhas de controle via AJAX
- **Leaderboard** de operadores por número de ações
- **Relatórios PDF** por operador com janela de tempo configurável
- **Relatório geral** gerado automaticamente ao encerrar o exercício
- **Timezone Brasília** (BRT -3) em todos os horários
- **Design cyberpunk** com tema escuro, fontes Share Tech Mono / Rajdhani / Exo 2

---

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, Flask 3.0 |
| ORM | SQLAlchemy 2.0 (classical mapping) |
| Banco | SQLite (padrão) / compatível com PostgreSQL |
| Frontend | Jinja2 + CSS puro + JavaScript vanilla |
| Testes | Pytest + FakeUnitOfWork |

---

## Pré-requisitos

- **Python 3.10 ou superior** ([download](https://www.python.org/downloads/))
- **pip** (já vem com o Python)
- **git** (para clonar o repositório)

Verifique se já tem instalado:

```bash
python3 --version
pip3 --version
```

---

## Instalação

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/redops.git
cd redops
```

### 2. Crie um ambiente virtual

```bash
python3 -m venv venv
```

### 3. Ative o ambiente virtual

**Linux / macOS:**
```bash
source venv/bin/activate
```

**Windows (cmd):**
```cmd
venv\Scripts\activate.bat
```

**Windows (PowerShell):**
```powershell
venv\Scripts\Activate.ps1
```

Quando ativado, você verá `(venv)` no início da linha do terminal.

### 4. Instale as dependências

```bash
pip install -r requirements.txt
```

### 5. Configure as variáveis de ambiente (opcional)

O projeto roda com valores padrão, mas você pode customizar:

**Linux / macOS:**
```bash
export DATABASE_URL=sqlite:///redteam.db
export SECRET_KEY=troque-esta-chave-em-producao
export ADMIN_USERNAME=admin
export ADMIN_PASSWORD=admin123
```

**Windows (cmd):**
```cmd
set DATABASE_URL=sqlite:///redteam.db
set SECRET_KEY=troque-esta-chave-em-producao
set ADMIN_USERNAME=admin
set ADMIN_PASSWORD=admin123
```

**Windows (PowerShell):**
```powershell
$env:DATABASE_URL="sqlite:///redteam.db"
$env:SECRET_KEY="troque-esta-chave-em-producao"
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="admin123"
```

> Se pular esta etapa, o sistema usa os valores padrão automaticamente (`admin` / `admin123`).

### 6. Execute o servidor

```bash
python wsgi.py
```

Você verá algo como:
```
 * Running on http://0.0.0.0:5000
```

### 7. Acesse no navegador

```
http://localhost:5000
```

---

## Variáveis de ambiente disponíveis

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | `sqlite:///redteam.db` | URL de conexão do banco |
| `SECRET_KEY` | `dev-secret-change-in-prod` | Chave secreta do Flask (sessões) |
| `ADMIN_USERNAME` | `admin` | Usuário do administrador |
| `ADMIN_PASSWORD` | `admin123` | **Altere antes de usar em produção!** |

---

## Parar o servidor

No terminal onde está rodando, pressione:
```
Ctrl + C
```

Para sair do ambiente virtual:
```bash
deactivate
```

---

## Rodar novamente depois (próximas vezes)

Você não precisa repetir toda a instalação — só ativar o ambiente virtual e rodar:

```bash
cd redops
source venv/bin/activate    # Linux/Mac
# venv\Scripts\activate.bat   # Windows cmd

python wsgi.py
```

---

## Arquitetura

Seguindo *Architecture Patterns with Python* (Percival & Gregory):

```
src/
├── domain/
│   ├── model.py          # Entidades, Value Objects, Eventos de domínio
│   └── ports.py          # Interfaces abstratas dos repositórios
├── adapters/
│   ├── orm/
│   │   └── mappings.py   # Mapeamento ORM clássico (ORM depende do modelo)
│   └── repository/
│       └── sqlalchemy_repos.py
├── service_layer/
│   ├── services.py       # Todos os use cases (trabalha só com primitivos)
│   └── unit_of_work.py   # UoW abstrato + SQLAlchemy + Fake (testes)
└── entrypoints/
    └── flask_app.py      # Flask blueprints (HTTP → service calls)
```

### Princípios aplicados

- **Inversão de dependência**: o ORM depende do modelo de domínio, nunca o contrário
- **Aggregate root**: `Exercise` é o agregado raiz — todas as mutações passam por ele
- **Repository Pattern**: a service layer nunca acessa SQLAlchemy diretamente
- **Unit of Work**: coordena repositórios e garante atomicidade
- **Fake UoW**: testes unitários sem banco de dados
- **Domain Events**: `AttackRegistered`, `ControlLineAchieved`, `ExerciseClosed`, etc.

---

## Guia de uso

### 1. Primeiro acesso — Admin

Acesse `http://localhost:5000/admin` e faça login com as credenciais configuradas (padrão: `admin` / `admin123`).

No primeiro acesso sem exercício ativo, o sistema redireciona automaticamente para o wizard de configuração.

<p align="center">
  <img src="docs/screenshots/admin_login.png" alt="Admin Login" width="400">
</p>

---

### 2. Wizard de configuração (5 passos)

#### Passo 1 — Exercício
Informe o nome e faça upload do logo (exibido no dashboard).

<p align="center">
  <img src="docs/screenshots/wizard_step1.png" alt="Wizard Step 1" width="700">
</p>

#### Passo 2 — Operadores
Crie as contas dos operadores Red Team (username + senha).

#### Passo 3 — Blue Teams
Crie os times defensores. Marque quais domínios participam (IT e/ou OT/SCADA).

#### Passo 4 — Cenários
Crie cenários com:
- **Máquinas alvo** (ex: DC01, SCADA-HMI-01)
- **Linhas de controle IT** (ex: Phishing entregue, Acesso inicial obtido)
- **Linhas de controle OT** (ex: Acesso à rede OT, Abertura de válvulas)

O mesmo cenário pode ser atribuído a múltiplos Blue Teams — o progresso é independente por time.

<p align="center">
  <img src="docs/screenshots/wizard_step4.png" alt="Wizard Step 4 - Scenarios" width="700">
</p>

#### Passo 5 — Atribuições
- Marque quais operadores atuam em cada Blue Team (matriz)
- Selecione qual cenário cada Blue Team utiliza

---

### 3. Área do Operador

Acesse `http://localhost:5000/operator` com as credenciais criadas pelo admin.

<p align="center">
  <img src="docs/screenshots/operator_dashboard.png" alt="Operator Dashboard" width="900">
</p>

#### Registrar ataque
Preencha:
- Blue Team alvo (se tiver mais de um atribuído)
- Máquina alvo (do cenário do BT)
- Sumário público (aparece no feed do dashboard)
- Descrição detalhada (aparece apenas no relatório)
- Horário (BRT -3, preenchido automaticamente)

#### Marcar linhas de controle
Na aba **Control Lines**, use o toggle para marcar/desmarcar cada linha atingida.
A marcação é feita via AJAX — **a página não recarrega**.

---

### 4. Dashboard público

Acesse `http://localhost:5000` — sem login necessário.

<p align="center">
  <img src="docs/screenshots/dashboard_full.png" alt="Dashboard" width="900">
</p>

Exibe:
- **Logo** do exercício em destaque
- **Barras de progresso** por Blue Team: segmento azul (IT) + vermelho (OT) em uma linha contínua, ordenadas por avanço
- **Detalhes** das linhas de controle por BT
- **Live Attack Feed** — últimos 20 ataques, atualizado a cada 5 segundos
- **Leaderboard** de operadores por número de ações

---

### 5. Relatório do operador

Acesse `http://localhost:5000/operator/report`.

Selecione o Blue Team e a janela de tempo → clique em **Generate PDF Report**.

Na página gerada, use `Ctrl+P` → "Salvar como PDF".

<p align="center">
  <img src="docs/screenshots/report.png" alt="Report" width="700">
</p>

---

### 6. Encerrar o exercício

No painel admin → **Close Exercise**.

O dashboard congela no estado final e o relatório completo fica disponível em `/admin/report/<exercise_id>`.

---

## Testes

```bash
# Com o ambiente virtual ativado
pip install pytest
python -m pytest tests/unit/ -v
```

Resultado esperado: **28 passed**

Os testes unitários usam `FakeUnitOfWork` — nenhum banco de dados é necessário para rodá-los.

---

## Rodando com Docker (alternativa)

Se preferir, o projeto também inclui suporte a Docker:

```bash
docker-compose up --build
# Acesse http://localhost:7331
```

Mas o método recomendado para desenvolvimento e uso simples é o ambiente virtual Python descrito acima.

---

## Estrutura de arquivos

```
redops/
├── src/
│   ├── domain/
│   │   ├── model.py              # Domínio puro
│   │   └── ports.py              # Interfaces
│   ├── adapters/
│   │   ├── orm/mappings.py       # ORM clássico SQLAlchemy
│   │   └── repository/           # Implementações concretas
│   ├── service_layer/
│   │   ├── services.py           # Use cases
│   │   └── unit_of_work.py       # UoW + Fake
│   └── entrypoints/
│       └── flask_app.py          # Flask + Blueprints
├── templates/
│   ├── base.html
│   ├── dashboard/
│   ├── operator/
│   ├── admin/
│   │   └── wizard/               # Steps 1-5
│   └── reports/
├── static/
│   ├── css/
│   └── img/                      # Logos (não versionado)
├── tests/
│   └── unit/
│       ├── test_domain_model.py
│       └── test_services.py
├── requirements.txt
├── wsgi.py
├── Dockerfile                    # Opcional
├── docker-compose.yml            # Opcional
└── README.md
```

---

## Referência arquitetural

Este projeto implementa os padrões descritos em:

> **Architecture Patterns with Python**
> Harry Percival & Bob Gregory — O'Reilly, 2020
> [https://www.cosmicpython.com](https://www.cosmicpython.com)

Capítulos aplicados:
- Cap. 1: Domain Modeling
- Cap. 2: Repository Pattern
- Cap. 4: Service Layer
- Cap. 5: TDD (High Gear and Low Gear)
- Cap. 6: Unit of Work
- Cap. 7: Aggregates

---

## Troubleshooting

**`python3` não é reconhecido (Windows)**
Use `python` no lugar de `python3`.

**Erro de permissão ao ativar o venv (PowerShell)**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**Porta 5000 já em uso**
```bash
export PORT=8080  # ou outra porta livre
python wsgi.py
```
*(nota: seria necessário ajustar o `wsgi.py` para ler a variável `PORT`)*

---

## Licença

MIT — veja [LICENSE](LICENSE) para detalhes.

---

<p align="center">
  Built with ⚡ for Red Team operations
</p>

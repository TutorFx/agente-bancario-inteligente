# 🏦 Banco Ágil — Sistema Bancário Multi-Agente de IA

Bem-vindo ao repositório do **Banco Ágil**, um sistema de atendimento bancário automatizado baseado em **Agentes de IA Especializados** e orquestrado com o **Google ADK (Agent Developer Kit)** e **Streamlit**.

O sistema foi desenvolvido para oferecer uma experiência de atendimento fluida e unificada ao cliente, em que a transição entre subagentes de **Triagem**, **Crédito**, **Entrevista Financeira** e **Câmbio** ocorre de forma **implícita e transparente**, mantendo rígidos controles de segurança, determinismo financeiro, auditabilidade regulatória e resiliência a acessos concorrentes.

---

## 📐 1. Visão Geral do Projeto

O projeto demonstra a aplicação prática de **Sistemas Multi-Agente (MAS)** no setor financeiro, combinando a versatilidade de Modelos de Linguagem (LLMs) com o determinismo de ferramentas de código Python para regras de crédito e integrações externas.

### 👥 Escopo e Atribuição dos Agentes
* 🤖 **Agente de Triagem (Host/Orquestrador):** Receptáculo primário da sessão. Realiza a saudação, coleta e validação de credenciais (CPF e Data de Nascimento) contra o cadastro em `clientes.csv`, sanitizando entradas e aplicando bloqueio definitivo na 3ª falha consecutiva.
* 💳 **Agente de Crédito:** Responsável por consultar limites atuais, processar solicitações de alteração de limite e validar o teto permitido via matriz de risco dinâmica (`data/score_limite.csv`).
* 🗣️ **Agente de Entrevista de Crédito:** Conduz uma entrevista financeira estruturada em 5 perguntas (Renda, Emprego, Despesas, Dependentes e Dívidas), aciona o motor determinístico de cálculo de score via Tool Python e persiste a pontuação atualizada.
* 💱 **Agente de Câmbio:** Consulta cotações de moedas em tempo real consumindo API financeira ao vivo via chamadas assíncronas com tratamento de timeout e guardrails de pré-validação de moedas.

---

## 🏗️ 2. Arquitetura do Sistema (DDD & SOLID)

A solução adota os princípios de **Domain-Driven Design (DDD)** e **SOLID** para garantir manutenibilidade, testabilidade e desacoplamento das regras de negócio em relação aos frameworks de IA:

- **Domain-Driven Design (DDD):**
  - `domain`: O coração do negócio, livre de frameworks externos. Contém DTOs, entidades e os motores de regra (ex: `guardrails.py` para cálculo de risco e validações).
  - `application`: Ferramentas (`tools`), subagentes (`subagents`) e manipuladores de caso de uso.
  - `infrastructure`: Adaptadores que gerenciam integrações externas, persistência em arquivos CSV com controle de trava (`BancoAgilAdapter`) e chamadas HTTP de câmbio.
- **Single Responsibility Principle (SRP):** Cada agente possui um papel único e escopo delimitado. O Agente de Crédito lida apenas com gestão de limites; o Agente de Câmbio foca exclusivamente na cotação de moedas.
- **Dependency Inversion Principle (DIP):** As ferramentas da LLM operam via interfaces e adaptadores, isolando a regra de negócio central da camada de orquestração do Google ADK.

### 🔄 Diagrama de Orquestração
```
                  ┌────────────────────────┐
                  │  Interface Streamlit   │
                  └───────────┬────────────┘
                              │ Request HTTP / REST
                 ┌────────────▼─────────────┐
                 │  🛡️ Input Middleware     │ (Regex + LLM Semântico)
                 └────────────┬─────────────┘
                              │
                  ┌───────────▼────────────┐
                  │   Google ADK Runner    │
                  └───────────┬────────────┘
                              │
               ┌──────────────┴──────────────┐
               │  🤖 Agente de Triagem (Host)│
               └──────────────┬──────────────┘
                              │ (Handoff Implícito)
     ┌────────────────────────┼────────────────────────┐
     │                        │                        │
┌────▼───────────┐   ┌────────▼───────────┐   ┌────────▼───────────┐
│ 💳 Agente de   │   │ 🗣️ Agente de       │   │ 💱 Agente de      │
│    Crédito     │   │    Entrevista      │   │    Câmbio          │
└────┬───────────┘   └────────┬───────────┘   └────────┬───────────┘
     │                        │                        │
     ├────────────────────────┴────────────────────────┤
     │                                                 │
┌────▼──────────────────────┐            ┌─────────────▼─────────────┐
│  🛡️ Output Middleware     │            │   Camada de Persistência  │
│(Anti-Vazamento/Alucinação)│            │     BancoAgilAdapter      │
└────┬──────────────────────┘            └─────────────┬─────────────┘
     │ Retorno ao Chat                                 │ FileLock
┌────▼──────────────────────┐            ┌─────────────▼─────────────┐
│    Interface Streamlit    │            │ Arquivos .CSV (Data Layer)│
└───────────────────────────┘            └───────────────────────────┘
```

---

## 🚀 3. Funcionalidades Implementadas

- [x] **Autenticação Segura:** Sanitização de CPF e validação contra `clientes.csv`, com limite de 3 tentativas incorretas por sessão.
- [x] **Matriz Dinâmica de Crédito:** Concessão parametrizada via `score_limite.csv` por faixas de pontuação, eliminando condicionais fixas (*hardcoded*).
- [x] **Modelo Ponderado por Categoria:** Cálculo de score calibrado com tetos individuais por componente (Renda, Emprego, Comprometimento, Dependentes e Dívidas), limitando o intervalo estritamente entre 0 e 1000 pontos.
- [x] **Trilha de Auditoria Regulatória:** Registro append-only de todas as transações de crédito com carimbo de data/hora em ISO 8601 UTC.
- [x] **Consultas de Câmbio em Tempo Real:** Chamadas assíncronas (`httpx`) à API do ExchangeRate com guardrails para validação prévia de moedas suportadas.
- [x] **Transição Implícita de Agentes:** Roteamento transparente no Google ADK, acompanhado por um painel lateral de telemetria para o avaliador no Streamlit.
- [x] **Reset de Sessão & Proteção PII:** Limpeza completa do estado e expurgamento de chaves no encerramento ("tchau"), com mensagens de erro que utilizam exemplos estáticos para evitar vazamento de dados de clientes.

---

## 🛠️ 4. Desafios Enfrentados e Soluções

1. **Distorção de Borda no Algoritmo de Score:**
   * *Desafio:* A razão ilimitada entre renda e despesas fazia com que rendas altas atingissem o teto de 1000 pontos isoladamente, anulando a penalidade de desemprego ou dívidas.
   * *Solução:* Migração para um modelo ponderado por categoria em `guardrails.py` com teto máximo individual por componente, comprovado via teste de borda unitário.
2. **Condições de Corrida no I/O do Streamlit:**
   * *Desafio:* Múltiplas requisições simultâneas causavam *lost updates* e arquivos CSV vazios durante sobrescritas.
   * *Solução:* Implementação de `FileLock` e gravação em arquivo temporário com substituição atômica (`os.replace`).
3. **Persistência de Sessão Pós-Despedida:**
   * *Desafio:* Enviar mensagens de encerramento mantinha o estado autenticado ativo para perguntas subsequentes.
   * *Solução:* Criação do mecanismo de reset síncrono que expurga as chaves de autenticação do `tool_context.state` e gera novo ID de sessão no Streamlit.

---

## 💡 5. Escolhas Técnicas e Justificativas de Design

| Decisão de Arquitetura | Justificativa Técnica / Benefício para o Negócio |
| :--- | :--- |
| **Framework Google ADK** | Permite isolar escopos e prompts em subagentes especializados, garantindo determinismo e facilitando a manutenção. |
| **Cálculo de Score via Tool Python** | Impede que a LLM estime ou invente pontuações de crédito, garantindo determinismo matemático absoluto. |
| **Fórmula de Risco por Categoria** | A aplicação de tetos por componente evita que clientes com rendas muito elevadas neutralizem penalidades relativas a desemprego ou dívidas ativas. |
| **`FileLock` + Escrita Atômica** | Elimina riscos de corrupção de arquivos planos em execuções concorrentes no Streamlit. |
| **Painel Lateral de Debug (`st.sidebar`)** | Separa a experiência do cliente (chat limpo) da visão de auditoria do avaliador (exibição do agente ativo e status de autenticação). |

### 🔒 Concorrência, Concessão de Crédito e Auditoria
Como o **Streamlit** executa requisições em múltiplas threads simultâneas, o adaptador de persistência (`BancoAgilAdapter`) foi blindado com técnicas de nível produtivo:
1. **Bloqueio Interprocessos (`FileLock`):** Instâncias de `_clientes_lock` e `_solicitacoes_lock` protegem o ciclo *Read-Modify-Write*, eliminando o problema de atualizações perdidas (*lost updates*).
2. **Escrita Atômica (`os.replace` + `os.fsync`):** Gravações em `clientes.csv` ocorrem primeiro em arquivos temporários com nivelamento de buffer em disco (`os.fsync`) antes da substituição atômica (`os.replace`), garantindo que o arquivo nunca seja truncado ou corrompido para 0 bytes em caso de falha.

### 📊 Governança Dinâmica de Crédito & Auditoria em UTC
> A concessão de ajuste de limite é gerenciada dinamicamente pela leitura da tabela de faixas de score (`data/score_limite.csv`) e estritamente auditada a cada requisição (seja aprovada ou rejeitada) no arquivo `data/solicitacoes_aumento_limite.csv` com timestamps em UTC no padrão **ISO 8601**. Em um ambiente de produção corporativo, essa camada de I/O baseada em arquivos seria desacoplada e conectada diretamente a um **Motor de Regras de Crédito (BRMS - Business Rules Management System)** via API REST e a um barramento de eventos (ex: Kafka / RabbitMQ) para auditoria transacional e governança em tempo real.

### 🛡️ Defense in Depth (Sanduíche de Guardrails)
O sistema adota o padrão de segurança corporativo de Defesa em Profundidade para blindar os agentes de inteligência artificial contra ataques de **Prompt Injection**, **Jailbreak** e **Prompt Leakage**:
1. **Input Guardrail Híbrido (`input_middleware.py`):** 
   - **Determinístico (Regex):** Bloqueia instantaneamente termos óbvios de override com latência zero.
   - **Semântico (LLM):** Inspeciona a intenção do usuário antes do roteamento, bloqueando tentativas de adoção de persona de autoridade (ex: "sou auditor do sistema") ou cálculos ilícitos.
2. **Output Guardrail Semântico (`output_middleware.py`):** Intercepta a resposta gerada pelo Agente antes de enviar ao usuário. Verifica se a IA não "alucinou" vazando nomes técnicos de ferramentas, instruções internas de prompt ou tratou de assuntos fora do escopo bancário.
3. **Prompts Enxutos:** Com as camadas externas garantindo a segurança, os *System Prompts* dos subagentes ficam limpos e focados exclusivamente na lógica de negócio e no bom atendimento, economizando tokens e reduzindo a latência global.

---

## 🚀 6. Começando (Tutorial de Execução e Testes)

Siga os passos abaixo para preparar e executar o ambiente de desenvolvimento.

### Pré-requisitos
* Python 3.10 ou superior
* Gerenciador de ambientes virtuais (`venv`)
* Chave de API do Google Gemini (gratuita no [Google AI Studio](https://aistudio.google.com/app/apikey))

### Passo a Passo de Instalação

1. **Clonar ou Baixar o Repositório:**
   ```bash
   # Opção A: Clonar via Git
   git clone https://github.com/TutorFx/agente-bancario-inteligente.git
   cd agente

   # Opção B: Se baixou o arquivo .zip do GitHub, extraia-o e acesse a pasta descompactada pelo terminal:
   cd agente
   ```

2. **Criar e Ativar o Ambiente Virtual:**
   * **Linux / macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
   * **Windows (PowerShell):**
     ```powershell
     # Se os scripts estiverem desabilitados no PowerShell, execute primeiro:
     Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```

3. **Instalar Dependências:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Configurar Variáveis de Ambiente:**
   Obtenha uma chave gratuita da API do Gemini em [Google AI Studio](https://aistudio.google.com/app/apikey). Em seguida, crie um arquivo chamado `.env` exatamente na raiz do projeto contendo:
   ```env
   GEMINI_API_KEY=sua_chave_gemini_aqui
   ```
   > 💡 **Dica (Windows):** Ao criar o arquivo pelo Bloco de Notas, certifique-se de salvar como `Todos os arquivos (*.*)` com o nome `.env`, para evitar que seja salvo incorretamente como `.env.txt`.

5. **Iniciar o Servidor Backend (API / Google ADK):**
   A interface web precisa da API do backend em execução para processar as mensagens. Em um terminal com o ambiente virtual ativado:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8085
   ```
   *(No Linux/macOS, você também pode executar `./run.sh`). Aguarde o log indicar que o servidor está rodando na porta `8085`.*

6. **Iniciar a Interface do Usuário (Streamlit UI):**
   Abra um **segundo terminal** (mantenha o terminal do backend rodando), navegue até a pasta do projeto, ative o ambiente virtual e execute:
   ```bash
   streamlit run streamlit_app.py
   ```
   Acesse a interface no navegador através do endereço local informado (geralmente `http://localhost:8501`).

   > 🛑 **Encerrar a Aplicação:** Para finalizar a execução a qualquer momento, pressione `Ctrl + C` em cada um dos dois terminais.

---

### 👤 Credenciais de Teste para Avaliação Rápida

Para testar o fluxo de autenticação e os cenários dos agentes no Streamlit ou via API, utilize qualquer uma das combinações de clientes cadastradas na base [`data/clientes.csv`](data/clientes.csv):

| Cliente | CPF (Com ou Sem Pontuação) | Data de Nascimento | Score Atual | Limite Atual | Conta | Cenário Sugerido |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **João Silva** *(Recomendado)* | `123.456.789-00` ou `12345678900` | `15/03/1985` | 824 | R$ 50.000,00 | 0001 | Score excelente e limite alto pré-aprovado |
| **Maria Santos** | `987.654.321-00` ou `98765432100` | `22/07/1990` | 580 | R$ 2.500,00 | 0002 | Score intermediário, ideal para aumento de limite ou entrevista |
| **Roberto Mendes** | `999.000.111-22` ou `99900011122` | `12/08/1975` | 450 | R$ 500,00 | 0009 | Score baixo, útil para testar limites e recálculo de pontuação |

> 💡 **Exemplo Rápido para Copiar e Colar no Chat quando solicitado:**
> * **CPF:** `123.456.789-00`
> * **Data de Nascimento:** `15/03/1985`
> 
> *Nota: O agente aceita o CPF tanto com máscara quanto apenas números. O sistema aplica bloqueio definitivo na 3ª tentativa incorreta consecutiva na mesma sessão.*

---

### 🧪 Execução da Suíte de Testes Automatizados

O projeto conta com uma suíte abrangente de testes unitários, de integração, de concorrência e de borda desenvolvida com `pytest`.

#### 1. Ativar o Ambiente Virtual
Certifique-se de estar com o ambiente virtual ativo no terminal:
* **Linux / macOS:** `source .venv/bin/activate`
* **Windows:** `.\.venv\Scripts\Activate.ps1`

#### 2. Executar a Suíte Completa com Relatório de Cobertura
Como os parâmetros já estão definidos no arquivo `pytest.ini`, basta executar:

```bash
# Executar todos os testes com validação de cobertura de código
pytest
```
*(Ou explicitamente: `pytest --cov=root_agent --cov-report=term-missing`)*

> ⚠️ **Anotação Importante sobre a Suíte Completa:**
> * **Chamadas E2E Reais:** A suíte inclui testes ponta a ponta (`tests/e2e/`) que exercitam o fluxo completo do agente integrando com o modelo Gemini. Por isso, a execução completa **requer conexão com a internet** e a variável `GEMINI_API_KEY` configurada no arquivo `.env`.
> * **Tempo de Execução:** A bateria completa com 39 testes leva aproximadamente **40 a 50 segundos** para concluir.
> * **Garantia de Qualidade:** A suíte valida 100% dos caminhos do motor de crédito (`guardrails.py`) e atinge **~85% de cobertura global**, superando com folga o limiar mínimo obrigatório de **75%** (`--cov-fail-under=75`).

#### 3. Execução Rápida (Apenas Testes Unitários - 100% Determinísticos)
Para validar toda a lógica de negócio, middlewares, presenters, guardrails e adapters instantaneamente (em ~1 segundo), sem depender de conexão de internet ou chaves de LLM:

```bash
pytest tests/unit/
```
> 🎯 **Cobertura Unitária Isolada:** Apenas os testes unitários já atingem **~91% de cobertura de código** (`root_agent`), superando a exigência de **75%** sem qualquer dependência externa ou não-determinismo.
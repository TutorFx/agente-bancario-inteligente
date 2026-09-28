# 🏦 Banco Ágil — Sistema Bancário Multi-Agente de IA

Bem-vindo ao repositório do **Banco Ágil**, um sistema de atendimento bancário automatizado baseado em **Agentes de IA Especializados** e orquestrado com o **Google ADK (Agent Developer Kit)** e **Streamlit**.

O sistema foi desenvolvido para oferecer uma experiência de atendimento fluida e unificada ao cliente, em que a transição entre subagentes de **Triagem**, **Crédito**, **Entrevista Financeira** e **Câmbio** ocorre de forma **implícita e transparente**, mantendo rígidos controles de segurança, determinismo financeiro, auditabilidade regulatória e resiliência a acessos concorrentes.

---

## 📐 1. Visão Geral do Projeto

O projeto demonstra a aplicação prática de **Sistemas Multi-Agente (MAS)** no setor financeiro, combinando a versatilidade de Modelos de Linguagem (LLMs) com o determinismo de ferramentas de código Python para regras de crédito e integrações externas.

### 👥 Escopo e Atribuição dos Agentes
* 🤖 **Agente de Triagem (Host/Orquestrador):** Receptáculo primário da sessão. Realiza a saudação, coleta e validação de credenciais (CPF e Data de Nascimento) contra o cadastro em `clientes.csv`, sanitizando entradas e encerrando/reiniciando a sessão na 3ª falha consecutiva.
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

- [x] **Autenticação Segura:** Sanitização de CPF e validação contra `clientes.csv`, com limite de 3 tentativas incorretas por sessão. *Testes:* `tests/unit/test_input_middleware.py`.
- [x] **Matriz Dinâmica de Crédito:** Concessão parametrizada via `score_limite.csv` por faixas de pontuação, eliminando condicionais fixas (*hardcoded*). *Testes:* `tests/integration/test_credito_adapter_integration.py`.
- [x] **Modelo Ponderado por Categoria:** Cálculo de score calibrado com tetos individuais por componente (Renda, Emprego, Comprometimento, Dependentes e Dívidas), limitando o intervalo estritamente entre 0 e 1000 pontos. *Testes:* `tests/unit/test_guardrails.py`.
- [x] **Trilha de Auditoria Regulatória:** Registro append-only de todas as transações de crédito com carimbo de data/hora em ISO 8601 UTC (`data/solicitacoes_aumento_limite.csv`). *Testes:* `tests/integration/test_credito_adapter_integration.py`.
- [x] **Consultas de Câmbio em Tempo Real:** Chamadas assíncronas (`httpx`) à API do ExchangeRate com guardrails para validação prévia de moedas suportadas. *Testes:* `tests/unit/test_cambio_tool.py` e `tests/unit/test_banco_agil_adapter.py`.
- [x] **Transição Implícita de Agentes:** Roteamento transparente no Google ADK, acompanhado por um painel lateral de telemetria para o avaliador no Streamlit (`st.sidebar` em `streamlit_app.py`).
- [x] **Reset de Sessão & Proteção PII:** Limpeza completa do estado e expurgamento de chaves no encerramento ("tchau"), com mensagens de erro que utilizam exemplos estáticos (`BankingPresenter`) para evitar vazamento de dados de clientes. *Testes:* `tests/unit/test_session_tool.py` e `tests/unit/test_banking_presenter.py`.

---

## 🛠️ 4. Desafios Enfrentados e Soluções

1. **Distorção de Borda no Algoritmo de Score:**
   * *Desafio:* A razão ilimitada entre renda e despesas fazia com que rendas altas atingissem o teto de 1000 pontos isoladamente, anulando a penalidade de desemprego ou dívidas.
   * *Solução:* Migração para um modelo ponderado por categoria em `guardrails.py` com teto máximo individual por componente: renda até 300 pts (raiz quadrada, saturando em R$ 30.000), emprego até 200 (CLT 200, autônomo 100, desempregado 0), comprometimento até 200, dependentes até 150 e dívidas até 150.
   * *Regras de borda:* (a) com renda ≤ 0 o comprometimento vale 0 pts, pois não há renda a comprometer (antes, renda e despesa zeradas concediam os 200 pts cheios e um desempregado sem renda chegava a 500 pts); (b) o score de desempregado tem teto de **600 pts**, independentemente da renda declarada, mantendo-o fora das faixas de limite ≥ 700 (antes, desempregado com R$ 50 mil de renda chegava a 800 pts). O corte é exposto no detalhamento como `ajuste_teto_desemprego`. Ambos os casos têm testes parametrizados em `tests/unit/test_guardrails.py`.
2. **Condições de Corrida no I/O do Streamlit:**
   * *Desafio:* Múltiplas requisições simultâneas causavam *lost updates* e arquivos CSV vazios durante sobrescritas.
   * *Solução:* Implementação de `FileLock` e gravação em arquivo temporário com substituição atômica (`os.replace`). *Testes:* escrita atômica e concorrência com `ThreadPoolExecutor` em `tests/unit/test_banco_agil_adapter.py`.
3. **Persistência de Sessão Pós-Despedida:**
   * *Desafio:* Enviar mensagens de encerramento mantinha o estado autenticado ativo para perguntas subsequentes.
   * *Solução:* Criação do mecanismo de reset síncrono que expurga as chaves de autenticação do `tool_context.state` (`session_tool.py`) e gera novo ID de sessão no Streamlit (`streamlit_app.py`). *Testes:* `tests/unit/test_session_tool.py`.

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
   - **Semântico (LLM):** Classifica a mensagem em 3 níveis — `SEGURO`, `FORA_DE_ESCOPO` (ex: pedido de código, receitas; segue para o `agente_fora_escopo`) e `ATAQUE` (persona de autoridade para mudar regras, pedido de prompt/ferramentas, dados de outros clientes). **Só `ATAQUE` encerra o atendimento.**
   - **Uma chamada por turno:** o veredito fica no estado da sessão (`temp:guardrail_entrada`, chaveado pelo `invocation_id`) e é reaproveitado pelos subagentes que recebem o turno por transferência. Mensagens só com números e pontuação (CPF, data, valores) dispensam a chamada.
2. **Output Guardrail (`output_middleware.py`):** Intercepta a resposta gerada pelo Agente antes de enviar ao usuário. A regex de termos internos (nomes de ferramentas, "system prompt") roda em toda resposta; a LLM só é consultada diante de sinal suspeito (bloco de código ou texto longo sem nenhum termo bancário).
   - **Política de falha explícita** (erro, timeout ou resposta fora do formato), configurável via `.env` (veja [`root_agent/config.py`](root_agent/config.py)): entrada *fail-closed* nos agentes de crédito/score e *fail-open* com log na conversa geral; saída *fail-closed*.
   - **Métricas:** cada chamada registra latência e contagem acumulada do turno no log (`guardrail.llm | ... latencia_ms=... chamadas_turno=...`).
3. **Prompts Enxutos:** Com as camadas externas garantindo a segurança, os *System Prompts* dos subagentes ficam limpos e focados exclusivamente na lógica de negócio e no bom atendimento, economizando tokens e reduzindo a latência global.

### 🔐 Autorização Determinística (não depende do prompt)
1. **Identidade só pela sessão (anti-IDOR):** as tools de crédito e score não recebem CPF da LLM; o cliente é resolvido exclusivamente a partir de `cliente_autenticado` no estado da sessão (`auth_guard.cpf_do_cliente_autenticado`).
2. **`before_tool_callback` nos subagentes:** qualquer tool de negócio (crédito, score, câmbio) é bloqueada enquanto `is_authenticated` não for `True`, mesmo que a LLM seja induzida a transferir o cliente.
3. **Autenticação determinística e *fail-closed*:** o `input_middleware` valida CPF + data de nascimento direto no `BancoAgilAdapter`, sem passar pela LLM. O login só é concedido diante de um retorno explícito de sucesso; erros técnicos não autenticam nem consomem tentativas.
4. **Estado protegido na API:** o `ProtectedStateMiddleware` rejeita (403) requisições que tentem definir chaves de autenticação via `state`/`stateDelta` nos endpoints REST do ADK.
5. **Minimização de PII:** CPF e data de nascimento nunca chegam ao provedor da LLM. A autenticação não usa tool, os prompts de sistema recebem apenas o nome do cliente, e CPFs/datas no histórico são mascarados antes de cada chamada (agentes e classificador semântico). As credenciais temporárias saem do estado logo após a validação, e a data de nascimento nunca é persistida.

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
   cd agente-bancario-inteligente

   # Opção B: Se baixou o arquivo .zip do GitHub, extraia-o e acesse a pasta descompactada pelo terminal
   # (o nome padrão do .zip é agente-bancario-inteligente-main):
   cd agente-bancario-inteligente-main
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
   Obtenha uma chave gratuita da API do Gemini em [Google AI Studio](https://aistudio.google.com/app/apikey). Em seguida, copie o modelo [`.env.example`](.env.example) para `.env` na raiz do projeto e preencha a chave:
   ```bash
   cp .env.example .env
   ```
   ```env
   GEMINI_API_KEY=sua_chave_gemini_aqui
   ```
   > As variáveis opcionais `LLM_MODEL_NAME`, `LLM_BASE_URL` e `LLM_API_KEY` permitem trocar o modelo/provedor via LiteLLM (padrão: `gemini/gemini-2.5-flash`).
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
| **João Silva** *(Recomendado)* | `123.456.789-00` ou `12345678900` | `15/03/1985` | 824 | R$ 50.000,00 | 0001 | Limite atual já acima do teto da matriz para o score (R$ 10.000,00): ideal para testar recusa de aumento e oferta de entrevista |
| **Maria Santos** | `987.654.321-00` ou `98765432100` | `22/07/1990` | 580 | R$ 2.500,00 | 0002 | Score intermediário, ideal para aumento de limite ou entrevista |
| **Roberto Mendes** | `999.000.111-22` ou `99900011122` | `12/08/1975` | 450 | R$ 500,00 | 0009 | Score baixo, útil para testar limites e recálculo de pontuação |

> 💡 **Exemplo Rápido para Copiar e Colar no Chat quando solicitado:**
> * **CPF:** `123.456.789-00`
> * **Data de Nascimento:** `15/03/1985`
> 
> *Nota: O agente aceita o CPF tanto com máscara quanto apenas números. Na 3ª tentativa incorreta consecutiva, o atendimento é encerrado e a sessão é reiniciada.*

---

### 🧪 Execução da Suíte de Testes Automatizados

O projeto tem uma suíte `pytest` dividida em três camadas:

| Camada | Pasta | Testes | O que cobre | Dependências externas |
| :--- | :--- | :---: | :--- | :--- |
| **Unitária** | `tests/unit/` | 222 | Domínio (`guardrails.py`), tools, middlewares, presenters, adapter (incluindo escrita atômica e concorrência com threads) | Nenhuma |
| **Integração** | `tests/integration/` | 8 | Tools de crédito + `BancoAgilAdapter` reais sobre CSVs temporários, sem mocks: matriz de score, persistência de limite e score, auditoria append-only em UTC. Chamadas de guardrail por turno no `InMemoryRunner` do ADK, com LLMs roteirizadas | Nenhuma |
| **E2E** | `tests/e2e/` | 6 | Autenticação e consulta mista via API do ADK com o modelo Gemini, conflito/fila de sessão e carregamento da UI Streamlit | Internet + `GEMINI_API_KEY` |

> Números de `pytest --collect-only -q`. Após alterar a suíte, atualize a tabela com essa saída.

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
> * **Chamadas E2E Reais:** os testes de `tests/e2e/` chamam o modelo Gemini. A execução completa **requer conexão com a internet** e a variável `GEMINI_API_KEY` configurada no arquivo `.env`.
> * **Tempo de Execução:** os 236 testes levam cerca de **30 segundos**, quase todo o tempo gasto nos E2E.
> * **Cobertura:** ~95% de cobertura de linhas em `root_agent`, com 100% em `guardrails.py`. O mínimo exigido é **75%** (`--cov-fail-under=75` em `pytest.ini`).

#### 3. Execução Rápida (Unitários + Integração, 100% Determinísticos)
Para validar lógica de negócio, middlewares, presenters, guardrails e adapter em ~1 segundo, sem internet nem chave de LLM:

```bash
pytest tests/unit/ tests/integration/
```
> 🎯 **Cobertura sem E2E:** unitários e integração juntos atingem **~96% de cobertura** de `root_agent` (só os unitários: ~96%), acima dos **75%** exigidos.

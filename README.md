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
* 💱 **Agente de Câmbio:** Consulta cotações de referência de moedas estrangeiras (o provedor atualiza uma vez por dia) via chamadas assíncronas, com tratamento de timeout e guardrails de pré-validação de moedas.

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
- [x] **Consultas de Câmbio (Cotação de Referência):** Chamadas assíncronas (`httpx`) à API do ExchangeRate, que atualiza as taxas uma vez por dia (a resposta informa a data da cotação). Guardrails validam a moeda antes da chamada (USD, EUR, GBP, ARS, JPY e CHF, todas presentes no provedor), e o cliente recebe mensagens distintas para "moeda indisponível no provedor" e "falha de rede/timeout". *Testes:* `tests/unit/test_cambio_tool.py` e `tests/unit/test_banco_agil_adapter.py`.
- [x] **Transição Implícita de Agentes:** Roteamento transparente no Google ADK, acompanhado por um painel lateral de telemetria para o avaliador no Streamlit (`st.sidebar` em `streamlit_app.py`).
- [x] **Reset de Sessão & Proteção PII:** Limpeza do estado no encerramento ("tchau"), no bloqueio após 3 tentativas e em `ATAQUE`, gravada no `state_delta` do evento e persistida pelo SessionService (a lista de chaves fica centralizada em `ESTADO_SEM_AUTENTICACAO`). Mensagens de erro usam exemplos estáticos (`BankingPresenter`) para evitar vazamento de dados de clientes. *Testes:* `tests/unit/test_session_tool.py`, `tests/integration/test_reset_sessao_persistido.py` e `tests/unit/test_banking_presenter.py`.

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
   * *Solução:* O reset grava `None` nas chaves de autenticação pela API pública do `State` (`resetar_autenticacao` em `conversation_state.py`). O ADK não apaga chaves do estado: o `state_delta` só sobrescreve, então `None` é o que limpa um valor. Uma versão anterior removia as chaves do `_delta` interno e o CPF continuava gravado no backend; os testes com `MagicMock` não pegavam o problema. O Streamlit também gera um novo ID de sessão. *Testes:* `tests/unit/test_session_tool.py` e `tests/integration/test_reset_sessao_persistido.py`, com `InMemorySessionService`, `InMemoryRunner` e leitura do estado persistido.

---

## 💡 5. Escolhas Técnicas e Justificativas de Design

| Decisão de Arquitetura | Justificativa Técnica / Benefício para o Negócio |
| :--- | :--- |
| **Framework Google ADK** | Permite isolar escopos e prompts em subagentes especializados, garantindo determinismo e facilitando a manutenção. |
| **Cálculo de Score via Tool Python** | Impede que a LLM estime ou invente pontuações de crédito, garantindo determinismo matemático. |
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
2. **`before_tool_callback` na triagem e nos subagentes:** qualquer tool de negócio (crédito, score, câmbio) é bloqueada enquanto `is_authenticated` não for `True`. Na triagem, o mesmo guard barra `transfer_to_agent` para os agentes especializados antes do login (só `agente_fora_escopo` fica liberado): com o histórico de um login anterior, a LLM chegava a transferir após o "tchau" mesmo com o prompt proibindo.
3. **Autenticação determinística e *fail-closed*:** o `input_middleware` valida CPF + data de nascimento direto no `BancoAgilAdapter`, sem passar pela LLM. O login só é concedido diante de um retorno explícito de sucesso; erros técnicos não autenticam nem consomem tentativas.
4. **Estado protegido na API:** o `ProtectedStateMiddleware` rejeita (403) requisições que tentem definir chaves de autenticação via `state`/`stateDelta` nos endpoints REST do ADK.
5. **Minimização de PII:** CPF e data de nascimento não chegam ao provedor da LLM. A autenticação não usa tool, os prompts de sistema recebem apenas o nome do cliente, e CPFs/datas no histórico são mascarados antes de cada chamada (agentes e classificador semântico). A máscara (`root_agent/domain/pii.py`) cobre todo formato de CPF aceito pelo login (com pontos, traços, barras ou espaços) e datas numéricas, ISO e por extenso ("15 de março de 1985"), sem mascarar valores em reais. O `MascaramentoCredenciaisPlugin` mascara a mensagem antes de o Runner gravá-la no histórico da sessão; o texto digitado fica só em memória (`temp:`) durante o turno. A data de nascimento nunca é persistida.
6. **API fechada por padrão:** a API REST do ADK não tem autenticação própria. Com `BANCO_AGIL_API_TOKEN` definido, toda rota (exceto `/health`) exige `Authorization: Bearer <token>`; sem ele, só conexões locais (loopback) são aceitas. As respostas de sessão e de execução saem sem CPF e data de nascimento (`RedacaoPiiMiddleware`), e o Streamlit gera um `user_id` aleatório por sessão do navegador.
7. **Dev UI do ADK opcional:** `/dev-ui` só é servida com `BANCO_AGIL_DEV_UI=true`.

> ⚠️ **Limite conhecido:** o CPF (só dígitos) continua no estado da sessão em `root_agent/.adk/session.db` enquanto o cliente está autenticado e no histórico de eventos depois disso, porque as tools resolvem o cliente por ele. A API não o expõe, mas quem tiver acesso ao arquivo consegue lê-lo. Em produção, o próximo passo seria cifrar esse valor ou trocá-lo por uma referência opaca.

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
   > Para acessar a API de outra máquina ou container, defina `BANCO_AGIL_API_TOKEN` no `.env` (o Streamlit envia o mesmo valor). `BANCO_AGIL_DEV_UI=true` liga a interface de desenvolvimento do ADK em `/dev-ui`.
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

O projeto tem uma suíte `pytest` dividida em quatro camadas:

| Camada | Pasta | Testes | O que cobre | Dependências externas |
| :--- | :--- | :---: | :--- | :--- |
| **Unitária** | `tests/unit/` | 367 | Domínio (`guardrails.py`), tools, middlewares, presenters, adapter (incluindo escrita atômica e concorrência com threads) | Nenhuma |
| **Integração** | `tests/integration/` | 19 | Tools de crédito + `BancoAgilAdapter` reais sobre CSVs temporários, sem mocks: matriz de score, persistência de limite e score, auditoria append-only em UTC. Chamadas de guardrail por turno e reset de sessão persistido no `InMemoryRunner` do ADK, com LLMs roteirizadas. API com token, redação de PII e credenciais fora do histórico da sessão | Nenhuma |
| **E2E** | `tests/e2e/` | 6 | Autenticação, encerramento e consulta mista via API do ADK com o modelo Gemini, conflito/fila de sessão e carregamento da UI Streamlit. As asserções usam sinais determinísticos dos eventos do `/run` (agente, transferências, tools, `stateDelta`), não o texto livre da LLM. Sem chave de API, os testes com LLM são pulados | Internet + `GEMINI_API_KEY` |
| **Avaliação (evals)** | `tests/evals/` | 53 cenários | Comportamento dos agentes com a LLM real: roteamento, tools e argumentos, estado final, dados persistidos e LLM como juiz. Fica fora do `pytest` padrão (ver [seção 7](#-7-avaliação-de-agentes-evals)) | Internet + `GEMINI_API_KEY` + `deepeval` |

> Números de `pytest --collect-only -q` (e de `pytest -m eval --collect-only -q` para os evals). Após alterar a suíte, atualize a tabela com essa saída.

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
> * **Tempo de Execução:** os 392 testes levam cerca de **30 segundos**, quase todo o tempo gasto nos E2E.
> * **Não determinismo:** os E2E que dependem de uma decisão da LLM repetem a conversa inteira uma vez (com aviso) antes de falhar; invariantes garantidas pelo código falham na hora.
> * **Cobertura:** ~97% de cobertura de linhas em `root_agent`, com 100% em `guardrails.py`. O mínimo exigido é **75%** (`--cov-fail-under=75` em `pytest.ini`).

#### 3. Execução Rápida (Unitários + Integração, 100% Determinísticos)
Para validar lógica de negócio, middlewares, presenters, guardrails e adapter em ~2 segundos, sem internet nem chave de LLM:

```bash
pytest tests/unit/ tests/integration/
```
> 🎯 **Cobertura sem E2E:** unitários e integração juntos atingem **~96% de cobertura** de `root_agent` (só os unitários: ~96%), acima dos **75%** exigidos.

---

## 📏 7. Avaliação de agentes (evals)

A cobertura de linhas mede o código Python, não o comportamento da LLM. A suíte em [`tests/evals/`](tests/evals/) mede, com a LLM real, se os agentes **roteiam para o agente certo, chamam as tools certas com os argumentos certos, deixam o estado correto e respondem sem expor a arquitetura interna**.

### Como funciona
* **Dataset** ([`tests/evals/dataset.yaml`](tests/evals/dataset.yaml)): 53 conversas roteirizadas em 9 categorias: roteamento por intenção, autenticação, recusa de aumento com oferta de entrevista, entrevista completa, correção de dado, câmbio (inclusive moeda inválida), tentativa de IDOR, jailbreak e encerramento ("tchau"). Cada turno declara o agente esperado, as tools com seus argumentos e padrões que a resposta deve ou não conter.
* **Execução isolada** ([`harness.py`](tests/evals/harness.py)): cada conversa roda em processo no `InMemoryRunner` do ADK, sobre uma cópia temporária de `data/` e com cotações fixas no lugar da API de câmbio. Nos cenários autenticados, o login passa pelo fluxo real (CPF e data de nascimento), que não chama a LLM.
* **Métricas determinísticas** ([`checks.py`](tests/evals/checks.py)), extraídas dos eventos do ADK:
  * `roteamento`: agente que respondeu (`author`) e transferências (`transfer_to_agent`);
  * `ferramentas`: tools chamadas, com os argumentos esperados, e tools proibidas no turno;
  * `estado`: estado final da sessão (`is_authenticated`, `entrevista_realizada_na_sessao`) e score/limite persistidos em `clientes.csv`;
  * `fidelidade_tools`: o número devolvido pela tool (ex.: `novo_score`) aparece na resposta;
  * `resposta`: padrões obrigatórios e proibidos em cada resposta;
  * `transicao_invisivel`: nenhuma resposta cita nomes de tools ou de agentes, instruções internas ou transferência.
* **LLM como juiz** ([`judge.py`](tests/evals/judge.py)): três métricas G-Eval do DeepEval, com o [`CustomGeminiEvaluator`](tests/utils/custom_evaluator.py) como juiz: `juiz_tom`, `juiz_sem_mencao_agentes` e `juiz_sem_numeros_inventados` (o juiz recebe os retornos das tools como contexto).
* **Não determinismo**: cada cenário roda `EVAL_RUNS` vezes (padrão: 3) e o relatório mostra a taxa de acerto média. O teste de um cenário passa com pelo menos 66% das execuções aprovadas; a sessão falha se alguma categoria ou métrica ficar abaixo do limiar definido no dataset (ex.: roteamento ≥ 95%, IDOR = 100%).

### Como executar
Os evals ficam fora do `pytest` padrão (marcador `eval` em `pytest.ini`) porque usam a LLM real, levam dezenas de minutos e têm custo de API:

```bash
pip install "deepeval>=4.0.6"   # juiz (DeepEval); o PyYAML já vem com o google-adk
pytest -m eval                  # 53 cenários × 3 execuções
EVAL_RUNS=1 pytest -m eval      # uma execução por cenário
EVAL_JUDGE=0 pytest -m eval     # só métricas determinísticas, sem LLM juiz
pytest -m eval -k cambio        # filtra cenários pelo id
```

O terminal mostra as taxas de acerto por categoria e por métrica. O relatório completo, com a taxa por cenário e as verificações que falharam, é gravado em `tests/evals/reports/latest.md`; as transcrições ficam em `latest.json` (ambos fora do git). Uma execução completa também reescreve o resumo publicado em [`tests/evals/results/RESULTS.md`](tests/evals/results/RESULTS.md) (`EVAL_PUBLICAR=1` força numa execução parcial).

As conversas rodam em série. Erros do provedor (429, timeout, 5xx) refazem a conversa inteira com espera crescente e são contabilizados à parte, sem virar falha de comportamento. Ajustes: `EVAL_PAUSA_SEGUNDOS` (ritmo para cotas baixas), `EVAL_TIMEOUT_CONVERSA`, `EVAL_TENTATIVAS`, `EVAL_ESPERA_RATE_LIMIT` e `EVAL_TIMEOUT_JUIZ`.

### Resultados da última execução

Execução completa em 28/09/2026 com `gemini/gemini-2.5-flash`, `EVAL_RUNS=1` e LLM como juiz: **44 de 53 conversas aprovadas (83%)**, em 15 minutos, com 399 chamadas à LLM e nenhum incidente de infraestrutura. Números completos em [`RESULTS.md`](tests/evals/results/RESULTS.md).

| Categoria | Acerto | Limiar |
| :--- | ---: | ---: |
| Autenticação, câmbio, correção de dado, entrevista, jailbreak, recusa com oferta de entrevista | 100% | 80–90% |
| Encerramento ("tchau") | 75% | 80% |
| IDOR | 60% | 100% |
| Roteamento | 54% | 95% |

Nas métricas determinísticas, `estado` (100%), `transicao_invisivel` (100%), `ferramentas` (96,8%) e `resposta` (94,2%) ficaram acima do limiar; `roteamento` ficou em 93,2% (limiar 95%).

**Leitura das 9 falhas:**
* **3 são o problema em aberto:** depois de `transfer_to_agent` para o `agente_credito`, o Gemini às vezes devolve conteúdo vazio e o cliente fica sem resposta no primeiro turno. O mesmo padrão ocorria após `encerrar_atendimento` e foi resolvido com uma despedida determinística; para o crédito, a correção ainda está pendente.
* **1 é parcial:** na pergunta mista ("meu limite e uma receita de bolo"), o agente responde o limite e ignora a parte fora do escopo.
* **5 foram reprovadas só pelo LLM juiz**, com todas as verificações determinísticas aprovadas. Nos 2 casos de IDOR, nenhum dado de terceiro foi exposto nem alterado; o juiz penalizou o tom (em um deles, confundiu qual cliente estava autenticado).

**O que os evals já corrigiram:** execuções anteriores revelaram um `{timestamp}` literal no prompt do câmbio, que o ADK tratava como variável de estado e fazia todo turno de câmbio falhar; o texto da recusa citando o "Agente de Entrevista"; a tool de encerramento devolvendo uma instrução interna que o modelo repetia ao cliente; e a despedida vazia após o "tchau". Todos têm teste offline hoje (por exemplo, `tests/unit/test_instrucoes_agentes.py` renderiza o prompt de cada agente com o motor de template do ADK).

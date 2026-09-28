# Banco Ágil: atendimento bancário multiagente

Sistema de atendimento bancário com agentes de IA, orquestrado com o **Google ADK (Agent Development Kit)** e com uma interface de testes em **Streamlit**.

O cliente conversa com um único assistente. Por trás dele, os agentes de **Triagem**, **Crédito**, **Entrevista de Crédito** e **Câmbio** trocam o turno entre si sem anunciar a transferência. Autenticação, cálculo de score e decisão de limite são feitos em código Python, não pela LLM.

---

## 1. Visão Geral do Projeto

A LLM conduz a conversa e escolhe o agente de cada assunto. As regras de crédito, a autenticação e as integrações ficam em tools e callbacks Python, com resultado previsível e testável.

### Escopo dos agentes
* **Agente de Triagem:** porta de entrada. Faz a saudação, coleta CPF e data de nascimento e os valida contra `clientes.csv`. Na 3ª falha consecutiva, encerra o atendimento.
* **Agente de Crédito:** informa o limite atual, processa pedidos de aumento e os valida pela tabela de faixas de score (`data/score_limite.csv`).
* **Agente de Entrevista de Crédito:** faz 5 perguntas (renda, emprego, despesas, dependentes e dívidas), calcula o novo score por uma tool Python e grava o resultado em `clientes.csv`.
* **Agente de Câmbio:** consulta cotações de referência na API pública do ExchangeRate, que atualiza as taxas uma vez por dia.

Um quinto agente, `agente_fora_escopo`, responde com uma recusa educada a pedidos sem relação com o banco.

---

## 2. Arquitetura do Sistema

O código está dividido em três camadas:

- `domain`: regras de negócio sem dependência do ADK. Contém os DTOs (Pydantic), a validação de CPF e datas, a regra de aumento de limite e a fórmula de score (`guardrails.py`), além da máscara de PII (`pii.py`).
- `application`: agentes (`subagents`), tools, callbacks do ADK (`middlewares`) e as mensagens fixas do atendimento (`presenters`).
- `infrastructure`: leitura e escrita dos CSVs com trava de arquivo, chamada HTTP de câmbio (`BancoAgilAdapter`), configuração do modelo e os middlewares HTTP da API.

As tools não acessam os arquivos diretamente: recebem o `BancoAgilAdapter` pelas funções de fábrica (`get_credito_tools`, `get_cambio_tool`), o que permite testá-las com um adapter falso.

### Fluxo de uma mensagem
```
 Streamlit ──HTTP──▶ API FastAPI (main.py)
                      │  middlewares HTTP: token, estado protegido,
                      │  fila por sessão, redação de PII
                      ▼
                     Runner do ADK
                      │
                      ▼
               Agente de Triagem ──transfer_to_agent──▶ Crédito | Entrevista | Câmbio | Fora de escopo
                      │                                  │
                      │  em cada agente:                 │
                      │  before_model_callback (login, guardrail de entrada, máscara de PII)
                      │  before_tool_callback  (exige cliente autenticado)
                      │  after_model_callback  (guardrail de saída, remove anúncio de transferência)
                      ▼                                  ▼
                            BancoAgilAdapter ──FileLock──▶ data/*.csv
                                             ──httpx────▶ open.er-api.com
```

---

## 3. Funcionalidades Implementadas

- [x] **Autenticação:** CPF (com ou sem pontuação) e data de nascimento validados contra `clientes.csv`, com até 3 tentativas consecutivas. A validação é feita no `input_middleware`, sem passar pela LLM. *Testes:* `tests/unit/test_input_middleware.py`.
- [x] **Limite por faixa de score:** o teto de cada faixa vem de `score_limite.csv`, não de condicionais no código. *Testes:* `tests/integration/test_credito_adapter_integration.py`.
- [x] **Score ponderado por categoria:** renda, emprego, comprometimento da renda, dependentes e dívidas, cada um com teto próprio, somando no máximo 1000 pontos. *Testes:* `tests/unit/test_guardrails.py`.
- [x] **Registro das solicitações de aumento:** cada pedido, aprovado ou rejeitado, é acrescentado a `data/solicitacoes_aumento_limite.csv` com data e hora em ISO 8601 (UTC). O status gravado é o final (`aprovado` ou `rejeitado`); o valor `pendente` não é usado, porque a decisão acontece na mesma chamada. *Testes:* `tests/integration/test_credito_adapter_integration.py`.
- [x] **Câmbio:** chamadas assíncronas (`httpx`) à API do ExchangeRate. A moeda é validada antes da chamada (USD, EUR, GBP, ARS, JPY e CHF), e o cliente recebe mensagens diferentes para "moeda indisponível no provedor" e "falha de rede/timeout". *Testes:* `tests/unit/test_cambio_tool.py` e `tests/unit/test_banco_agil_adapter.py`.
- [x] **Transição entre agentes sem anúncio:** os prompts proíbem anunciar a transferência, e o `after_model_callback` remove frases como "vou transferir você para o agente de crédito" se a LLM escrevê-las. A barra lateral do Streamlit mostra o agente ativo, como informação de depuração para quem testa.
- [x] **Reset de sessão:** no encerramento ("tchau"), no bloqueio após 3 tentativas e em mensagens classificadas como `ATAQUE`, as chaves de autenticação são limpas no `state_delta` do evento e persistidas pelo SessionService (lista em `ESTADO_SEM_AUTENTICACAO`). *Testes:* `tests/unit/test_session_tool.py` e `tests/integration/test_reset_sessao_persistido.py`.

---

## 4. Desafios Enfrentados e Soluções

1. **Score distorcido em casos extremos:**
   * *Desafio:* na primeira versão, a razão entre renda e despesas não tinha limite, e uma renda alta sozinha levava o score a 1000, anulando a penalidade por desemprego ou dívidas.
   * *Solução:* cada componente passou a ter um teto em `guardrails.py`: renda até 300 pts (raiz quadrada, saturando em R$ 30.000), emprego até 200 (CLT 200, autônomo 100, desempregado 0), comprometimento até 200, dependentes até 150 e dívidas até 150.
   * *Regras de borda:* (a) com renda ≤ 0, o comprometimento vale 0 pts (antes, renda e despesa zeradas davam os 200 pts cheios, e um desempregado sem renda chegava a 500 pts); (b) o score de desempregado tem teto de **600 pts**, o que o mantém fora das faixas de limite a partir de 700 (antes, um desempregado com R$ 50 mil de renda chegava a 800 pts). O corte aparece no detalhamento como `ajuste_teto_desemprego`. Os dois casos têm testes parametrizados em `tests/unit/test_guardrails.py`.
2. **Concorrência na escrita dos CSVs:**
   * *Desafio:* a API atende requisições em paralelo, e duas escritas simultâneas em `clientes.csv` podiam perder uma atualização ou deixar o arquivo vazio durante a sobrescrita.
   * *Solução:* `FileLock` em volta de cada ciclo de leitura e escrita, e gravação em arquivo temporário seguida de `os.replace`. *Testes:* escrita atômica e concorrência com `ThreadPoolExecutor` em `tests/unit/test_banco_agil_adapter.py`.
3. **Sessão autenticada após a despedida:**
   * *Desafio:* depois do "tchau", o estado autenticado continuava ativo para as perguntas seguintes.
   * *Solução:* o reset grava `None` nas chaves de autenticação pela API pública do `State` (`resetar_autenticacao` em `conversation_state.py`). O ADK não apaga chaves do estado: o `state_delta` só sobrescreve, então `None` é o que limpa um valor. Uma versão anterior removia as chaves do `_delta` interno, e o CPF continuava gravado no backend; os testes com `MagicMock` não pegavam o problema. O Streamlit também gera um novo ID de sessão. *Testes:* `tests/unit/test_session_tool.py` e `tests/integration/test_reset_sessao_persistido.py`, com `InMemorySessionService`, `InMemoryRunner` e leitura do estado persistido.

---

## 5. Escolhas Técnicas e Justificativas

| Decisão | Justificativa |
| :--- | :--- |
| **Google ADK** | Cada agente tem prompt, tools e callbacks próprios, e a transferência entre eles (`transfer_to_agent`) já vem pronta. |
| **Score calculado por tool Python** | A LLM coleta as respostas; o número vem de uma fórmula fixa e testada. |
| **Tetos por componente do score** | Impedem que uma renda muito alta compense sozinha desemprego ou dívidas. |
| **`FileLock` e escrita atômica** | Evitam atualizações perdidas e arquivos truncados quando há requisições simultâneas. |
| **Barra lateral de depuração (`st.sidebar`)** | Mostra o agente ativo e o status de autenticação para quem testa, sem colocar essas informações no chat. |

### Persistência
O `BancoAgilAdapter` protege os CSVs de duas formas:
1. **`FileLock`:** as travas `_clientes_lock` e `_solicitacoes_lock` cobrem o ciclo de leitura, alteração e escrita, para que duas requisições não sobrescrevam a alteração uma da outra.
2. **Escrita atômica:** `clientes.csv` é gravado primeiro num arquivo temporário (com `os.fsync`) e depois substituído com `os.replace`, de modo que uma falha no meio da escrita não deixa o arquivo truncado.

Em produção, os CSVs seriam trocados por um banco de dados, e a decisão de limite, por um serviço de regras de crédito.

### Guardrails de entrada e saída
1. **Entrada (`input_middleware.py`):**
   - **Regex:** bloqueia padrões explícitos de prompt injection ("ignore as instruções", "system prompt"), sem chamar a LLM.
   - **Classificador (LLM):** classifica a mensagem em `SEGURO`, `FORA_DE_ESCOPO` (receitas, pedidos de código etc., que seguem para o `agente_fora_escopo`) ou `ATAQUE` (persona de autoridade para mudar regras, pedido de prompt ou ferramentas, dados de outros clientes). Só `ATAQUE` encerra o atendimento.
   - **Uma chamada por turno:** o veredito fica no estado (`temp:guardrail_entrada`, chaveado pelo `invocation_id`) e é reaproveitado pelos agentes que recebem o turno por transferência. Mensagens só com números e pontuação (CPF, data, valores) não chamam o classificador.
2. **Saída (`output_middleware.py`):** uma regex barra nomes de tools e termos internos em toda resposta. A LLM só é consultada quando há sinal suspeito (bloco de código, ou texto longo sem nenhum termo bancário).
   - **Política de falha** (erro, timeout ou resposta fora do formato), configurável no `.env` (veja [`root_agent/config.py`](root_agent/config.py)): na entrada, bloqueia nos agentes de crédito e score e deixa passar, com log, na conversa geral; na saída, bloqueia.
   - **Métricas:** cada chamada registra no log a latência e a contagem de chamadas do turno (`guardrail.llm | ... latencia_ms=... chamadas_turno=...`).

### Autorização (fora do prompt)
1. **Cliente identificado só pela sessão:** as tools de crédito e score não recebem CPF da LLM; o cliente vem de `cliente_autenticado` no estado da sessão (`auth_guard.cpf_do_cliente_autenticado`). Isso impede que um cliente consulte ou altere dados de outro.
2. **`before_tool_callback` em todos os agentes com tools:** as tools de crédito, score e câmbio ficam bloqueadas enquanto `is_authenticated` não for `True`. Na triagem, o mesmo callback barra `transfer_to_agent` para os agentes especializados antes do login (só `agente_fora_escopo` fica liberado): com o histórico de um login anterior, a LLM chegava a transferir depois do "tchau", mesmo com o prompt proibindo.
3. **Autenticação sem LLM:** o `input_middleware` valida CPF e data de nascimento direto no `BancoAgilAdapter`. O login só é concedido com um retorno explícito de sucesso; erros técnicos não autenticam nem contam como tentativa.
4. **Estado protegido na API:** o `ProtectedStateMiddleware` recusa (403) requisições que tentem definir chaves de autenticação via `state`/`stateDelta` nos endpoints REST do ADK.
5. **PII fora da LLM:** CPF e data de nascimento não são enviados ao provedor da LLM. A autenticação não usa tool, os prompts recebem só o nome do cliente, e CPFs e datas no histórico são mascarados antes de cada chamada (agentes e classificador). A máscara (`root_agent/domain/pii.py`) cobre os formatos de CPF aceitos no login (com pontos, traços, barras ou espaços) e datas numéricas, ISO e por extenso ("15 de março de 1985"), sem mascarar valores em reais. O `MascaramentoCredenciaisPlugin` mascara a mensagem antes de o Runner gravá-la no histórico; o texto original fica só em memória (`temp:`) durante o turno. A data de nascimento não é persistida.
6. **API fechada por padrão:** a API REST do ADK não tem autenticação própria. Com `BANCO_AGIL_API_TOKEN` definido, toda rota (exceto `/health`) exige `Authorization: Bearer <token>`; sem ele, só conexões locais (loopback) são aceitas. As respostas de sessão e de execução saem sem CPF e data de nascimento (`RedacaoPiiMiddleware`), e o Streamlit gera um `user_id` aleatório por sessão do navegador.
7. **Dev UI do ADK opcional:** `/dev-ui` só é servida com `BANCO_AGIL_DEV_UI=true`.

> **Limitações conhecidas:**
> * O CPF (só dígitos) fica no estado da sessão em `root_agent/.adk/session.db` enquanto o cliente está autenticado, e no histórico de eventos depois disso, porque as tools identificam o cliente por ele. A API não o expõe, mas quem tiver acesso ao arquivo consegue lê-lo. Em produção, o próximo passo seria cifrar esse valor ou trocá-lo por uma referência opaca.
> * O limite de 3 tentativas vale por atendimento: depois do bloqueio, o contador volta a zero e uma nova sessão pode tentar de novo. Não há bloqueio por CPF nem limite de taxa.

---

## 6. Tutorial de Execução e Testes

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
   > **Windows:** ao criar o arquivo pelo Bloco de Notas, salve como `Todos os arquivos (*.*)` com o nome `.env`, para que ele não fique como `.env.txt`.

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

   > Para encerrar, pressione `Ctrl + C` nos dois terminais.

---

### Credenciais de teste

Para testar no Streamlit ou via API, use qualquer cliente cadastrado em [`data/clientes.csv`](data/clientes.csv):

| Cliente | CPF (Com ou Sem Pontuação) | Data de Nascimento | Score Atual | Limite Atual | Conta | Cenário Sugerido |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **João Silva** *(Recomendado)* | `123.456.789-00` ou `12345678900` | `15/03/1985` | 824 | R$ 50.000,00 | 0001 | Limite atual acima do teto da faixa do score (R$ 10.000,00): qualquer pedido de aumento é recusado, com oferta de entrevista |
| **Maria Santos** | `987.654.321-00` ou `98765432100` | `22/07/1990` | 580 | R$ 2.500,00 | 0002 | Score intermediário: aumento de limite ou entrevista |
| **Roberto Mendes** | `999.000.111-22` ou `99900011122` | `12/08/1975` | 450 | R$ 500,00 | 0009 | Score baixo: limites e recálculo de score |

> **Para copiar e colar no chat:**
> * **CPF:** `123.456.789-00`
> * **Data de Nascimento:** `15/03/1985`
> 
> O CPF pode ser digitado com ou sem pontuação. Na 3ª tentativa incorreta consecutiva, o atendimento é encerrado e a sessão é reiniciada.

---

### Testes automatizados

O projeto tem uma suíte `pytest` dividida em quatro camadas:

| Camada | Pasta | Testes | O que cobre | Dependências externas |
| :--- | :--- | :---: | :--- | :--- |
| **Unitária** | `tests/unit/` | 367 | Domínio (`guardrails.py`), tools, middlewares, presenters, adapter (incluindo escrita atômica e concorrência com threads) | Nenhuma |
| **Integração** | `tests/integration/` | 19 | Tools de crédito + `BancoAgilAdapter` reais sobre CSVs temporários, sem mocks: matriz de score, persistência de limite e score, auditoria append-only em UTC. Chamadas de guardrail por turno e reset de sessão persistido no `InMemoryRunner` do ADK, com LLMs roteirizadas. API com token, redação de PII e credenciais fora do histórico da sessão | Nenhuma |
| **E2E** | `tests/e2e/` | 6 | Autenticação, encerramento e consulta mista via API do ADK com o modelo Gemini, conflito/fila de sessão e carregamento da UI Streamlit. As asserções usam sinais determinísticos dos eventos do `/run` (agente, transferências, tools, `stateDelta`), não o texto livre da LLM. Sem chave de API, os testes com LLM são pulados | Internet + `GEMINI_API_KEY` |
| **Avaliação (evals)** | `tests/evals/` | 53 cenários | Comportamento dos agentes com a LLM real: roteamento, tools e argumentos, estado final, dados persistidos e LLM como juiz. Fica fora do `pytest` padrão (ver [seção 7](#7-avaliação-de-agentes-evals)) | Internet + `GEMINI_API_KEY` + `deepeval` |

> Números de `pytest --collect-only -q` (e de `pytest -m eval --collect-only -q` para os evals). Após alterar a suíte, atualize a tabela com essa saída.

#### 1. Ativar o Ambiente Virtual
Com o ambiente virtual ativo no terminal:
* **Linux / macOS:** `source .venv/bin/activate`
* **Windows:** `.\.venv\Scripts\Activate.ps1`

#### 2. Executar a Suíte Completa com Relatório de Cobertura
Os parâmetros estão em `pytest.ini`:

```bash
# Executar todos os testes com validação de cobertura de código
pytest
```
*(Ou explicitamente: `pytest --cov=root_agent --cov-report=term-missing`)*

> **Sobre a suíte completa:**
> * **Chamadas E2E Reais:** os testes de `tests/e2e/` chamam o modelo Gemini. A execução completa **requer conexão com a internet** e a variável `GEMINI_API_KEY` configurada no arquivo `.env`.
> * **Tempo de Execução:** os 392 testes levam cerca de **30 segundos**, quase todo o tempo gasto nos E2E.
> * **Não determinismo:** os E2E que dependem de uma decisão da LLM repetem a conversa inteira uma vez (com aviso) antes de falhar; invariantes garantidas pelo código falham na hora.
> * **Cobertura:** ~97% de cobertura de linhas em `root_agent`, com 100% em `guardrails.py`. O mínimo exigido é **75%** (`--cov-fail-under=75` em `pytest.ini`).

#### 3. Só unitários e integração (sem LLM)
Roda em poucos segundos, sem internet nem chave de LLM:

```bash
pytest tests/unit/ tests/integration/
```
> Unitários e integração juntos cobrem cerca de 97% das linhas de `root_agent`.

---

## 7. Avaliação de agentes (evals)

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
| Autenticação, câmbio, correção de dado, entrevista, jailbreak, recusa com oferta de entrevista | 100% | 80% a 90% |
| Encerramento ("tchau") | 75% | 80% |
| IDOR | 60% | 100% |
| Roteamento | 54% | 95% |

Nas métricas determinísticas, `estado` (100%), `transicao_invisivel` (100%), `ferramentas` (96,8%) e `resposta` (94,2%) ficaram acima do limiar; `roteamento` ficou em 93,2% (limiar 95%).

**Leitura das 9 falhas:**
* **3 são o problema em aberto:** depois de `transfer_to_agent` para o `agente_credito`, o Gemini às vezes devolve conteúdo vazio e o cliente fica sem resposta no primeiro turno. O mesmo padrão ocorria após `encerrar_atendimento` e foi resolvido com uma despedida determinística; para o crédito, a correção ainda está pendente.
* **1 é parcial:** na pergunta mista ("meu limite e uma receita de bolo"), o agente responde o limite e ignora a parte fora do escopo.
* **5 foram reprovadas só pelo LLM juiz**, com todas as verificações determinísticas aprovadas. Nos 2 casos de IDOR, nenhum dado de terceiro foi exposto nem alterado; o juiz penalizou o tom (em um deles, confundiu qual cliente estava autenticado).

**O que os evals já corrigiram:** execuções anteriores revelaram um `{timestamp}` literal no prompt do câmbio, que o ADK tratava como variável de estado e fazia todo turno de câmbio falhar; o texto da recusa citando o "Agente de Entrevista"; a tool de encerramento devolvendo uma instrução interna que o modelo repetia ao cliente; e a despedida vazia após o "tchau". Todos têm teste offline hoje (por exemplo, `tests/unit/test_instrucoes_agentes.py` renderiza o prompt de cada agente com o motor de template do ADK).

# Especificação Técnica: VoiceClaw Agent System (J.A.R.V.I.S. V2)

## 1. Visão Geral
O VoiceClaw é um assistente de codificação por voz que utiliza múltiplos provedores de LLM para executar tarefas complexas de desenvolvimento através de uma arquitetura de agentes nativa e agnóstica.

## 2. Arquitetura de Execução (AgentRunner)
O componente central é o `AgentRunner`, que orquestra a comunicação com diferentes provedores de LLM e a execução de ferramentas locais.

### 2.1 Provedores Suportados
| Provedor | SDK / Protocolo | Endpoint Base | Variável de API |
| :--- | :--- | :--- | :--- |
| **Google** | `google-genai` | Nativo | `GEMINI_API_KEY` |
| **NVIDIA** | `openai` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_API_KEY` |
| **OpenRouter** | `openai` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` |

### 2.2 Identificação de Modelos
Os modelos serão identificados por um prefixo de provedor para facilitar o roteamento:
- `google/gemini-2.0-flash`
- `nvidia/deepseek-ai/deepseek-v3`
- `nvidia/deepseek-ai/deepseek-r1`
- `nvidia/microsoft/phi-4`
- `openrouter/anthropic/claude-3.5-sonnet`

## 3. Protocolo de Ferramentas (Tool Calling)
O sistema expõe ferramentas locais para que o agente possa interagir com o sistema de arquivos e o terminal do usuário.

### 3.1 Definições de Ferramentas
- `run_bash(command: str)`: Executa comandos no terminal local.
- `read_file(path: str)`: Lê o conteúdo de um arquivo.
- `write_file(path: str, content: str)`: Escreve ou sobrescreve um arquivo.
- `list_files(path: str)`: Lista arquivos em um diretório.

### 3.2 Automação de Desktop (Novo)
O sistema permite o controle direto da interface gráfica e monitoramento persistente:
- `computer_control(action: str, ...)`: Controle de mouse (click, move) e teclado (type, press, hotkey) via PyAutoGUI. Inclui `screenshot` com redimensionamento automático para alinhar coordenadas físicas e lógicas.
- `launch_app(name: str)`: Abertura robusta de aplicativos Windows via subprocesso.
- `manage_background_task(action: str, instruction: str)`: Execução de loops de monitoramento em threads separadas para não bloquear a interface de voz.

### 3.3 Tradução de Formatos
O `AgentRunner` deve traduzir as definições de ferramentas:
- **Formato Google**: Dicionários seguindo o esquema `google-genai`.
- **Formato OpenAI (NVIDIA/OpenRouter)**: Esquema JSON Schema padrão para `tools` e `tool_choice`.

## 4. Fluxo de Trabalho
1. **Entrada**: Usuário envia áudio PCM via WebSocket.
2. **Transcrição**: O `STTService` (Gemini) converte áudio em texto.
3. **Roteamento**: O `server.py` encaminha o texto e o modelo selecionado para o `AgentRunner`.
4. **Loop de Agente**:
   - O LLM analisa a tarefa e decide chamar uma ferramenta.
   - O `AgentRunner` executa a ferramenta localmente (ex: `bash`).
   - O resultado é enviado de volta ao LLM.
   - O processo repete até que a tarefa seja concluída.
5. **Saída**: O progresso e a resposta final são transmitidos via WebSocket em tempo real.

## 5. Requisitos de Ambiente (.env)
```env
GEMINI_API_KEY=...
NVIDIA_API_KEY=...
OPENROUTER_API_KEY=...
PORT=8000
PROJECT_DIR=...
```

## 6. Frontend
- Seletor de modelos dinâmico alimentado pelo endpoint `/api/models`.
- Visualização de logs de ferramentas para transparência na execução de comandos bash.

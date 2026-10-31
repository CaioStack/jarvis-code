# 🧠 Jarvis-Code - Assistente Virtual Inteligente

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![CI](https://img.shields.io/github/actions/workflow/status/CaioStack/jarvis-code/ci.yml?branch=main)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status: Em Desenvolvimento](https://img.shields.io/badge/Status-Em%20Desenvolvimento-brightgreen.svg)

**Jarvis-Code** é um sistema de Inteligência Artificial modular, altamente customizável e expansível, desenvolvido totalmente em Python. Inspirado no icônico assistente virtual, este projeto foi desenhado para ser um núcleo de IA capaz de gerenciar memória, executar ações complexas, integrar-se com provedores externos de LLMs e oferecer uma interface de controle intuitiva.

## ✨ Funcionalidades Principais

* 🧩 **Arquitetura Modular:** Sistema construído de forma segmentada para facilitar a escalabilidade e a manutenção.
* 🔌 **Sistema de Plugins:** Adicione novas capacidades e ferramentas à IA de forma dinâmica, sem alterar o código principal.
* 🧠 **Gerenciamento de Memória:** Capacidade de retenção de contexto, permitindo conversas fluidas e lembrança de interações passadas.
* 🌐 **Integração com Provedores:** Suporte facilitado para diferentes APIs e modelos de linguagem (OpenAI, Gemini, Ollama, etc.).
* ⚡ **Ações Customizadas:** Definição de fluxos de trabalho e comandos específicos que a IA pode executar no sistema operacional ou na web.
* 🖥️ **Interface Própria (`ui.py` e `dashboard`):** Interface visual e painel de controle para monitoramento, configuração e interação com o núcleo da IA.

## 🏗️ Arquitetura

### Duas maneiras de conversar

O Jarvis-Code pode falar com um modelo de duas formas, e o restante do aplicativo (avatar, memória, desfazer, ações, plugins, painel) não sabe qual delas está em uso:

1. **Gemini Live (direto)** — um único soquete leva áudio de entrada, áudio de saída, transcrições e chamadas de ferramenta juntos; o servidor decide quando o turno termina. É o caminho de menor latência (cerca de 0,3–0,6 s).
2. **Pipeline local (STT → LLM → TTS)** — `providers/engine_pipeline.py` monta reconhecimento de fala, modelo de linguagem e síntese de voz atrás da mesma interface que a sessão Live usa. É o caminho que continua funcionando sem cota da API, com a rede fora ou com áudio que não pode sair do computador. Custa cerca de 1,5–4 s por turno porque as três etapas ocorrem em série.

### O que o pipeline local faz

* **Fim de turno pelo áudio** — o detetor de atividade de voz (VAD) mede o ruído ambiente continuamente e encerra o turno quando o silêncio dura cerca de 700 ms, depois de um mínimo de fala. Nada é transcrito enquanto a pessoa ainda fala.
* **Filtro de raciocínio** — modelos locais (qwen3, deepseek-r1 e distilações) pensam em voz alta dentro de blocos de raciocínio; o filtro remove esses blocos antes de falar, registrar no log ou gravar no histórico, para o assistente não ler o próprio raciocínio em voz alta.
* **Orçamento de histórico** — como uma API de chat sem estado não comprime o contexto, o pipeline guarda uma janela de caracteres (padrão: 24.000) das trocas recentes, sem cortar no meio de uma troca.
* **Chamadas de ferramenta seguras** — chamadas repetidas com os mesmos argumentos são respondidas com o resultado da primeira vez (evita, por exemplo, abrir o WhatsApp quatro vezes) e um turno encerra depois de no máximo quatro rodadas de ferramenta, para um modelo que vagueia não travar a conversa.
* **Voz por idioma** — a TTS recebe o idioma detectado na fala quando a voz suporta. Emojis são removidos apenas do que é falado, nunca do log nem do histórico.

### Ações e plugins

Novas capacidades chegam sem tocar no núcleo:

* **Ações** (`core/action_loader.py`, pasta `actions/`) — declarações com metadados (`tier`, `brief`) carregadas automaticamente; cada ação registra como se desfaz.
* **Plugins** (`core/plugin_loader.py`, pasta `plugins/`) — extensões isoladas; cada qual importa suas dependências apenas no momento de uso, para um plugin sem dependências instaladas não impedir o resto do aplicativo.

### Desfazer

`core/undo.py` mantém uma pilha compartilhada (`push_undo`, `undo_last`, `peek`, `history`, `clear`, profundidade 10): o assistente age imediatamente e registra como reverter, então "desfaz isso" reverte efetivamente a última ação.

### Fluxo de um turno

Microfone bufferizado → fim de turno (VAD ou soltar o push-to-talk) → STT transcreve → é emitido como "Você: ..." → o modelo responde frase a frase, e cada frase já é enviada para a voz enquanto chega → se o modelo chamar uma ferramenta, o aviso ("um instante") é falado antes, a ferramenta roda e o resultado volta ao histórico. O turno só termina quando a resposta chega ao fim.

## 📂 Estrutura do Projeto

Abaixo está o mapeamento exato da arquitetura do projeto:

```text
📦 jarvis-code
 ┣ 📂 actions/         # Declarações de ações que a IA pode executar
 ┣ 📂 config/          # Configuração (api_keys.json não é versionado; veja api_keys.example.json)
 ┣ 📂 core/            # Cérebro: orquestração, desfazer, carregador de ações/plugins
 ┣ 📂 dashboard/       # Painel de controle remoto (FastAPI)
 ┣ 📂 memory/          # Persistência de contexto e memória
 ┣ 📂 plugins/         # Extensões de habilidades isoladas
 ┣ 📂 providers/       # Conectores de LLM, TTS/STT e o pipeline local
 ┣ 📂 tests/           # Testes pytest (desfazer, schema, carregador de ações)
 ┣ 📂 .github/         # Integração contínua (CI)
 ┣ 📜 LICENSE          # Termos de licença de uso do software
 ┣ 📜 main.py          # Ponto de entrada do núcleo da aplicação
 ┣ 📜 pyproject.toml   # Empacotamento e metadados do projeto
 ┣ 📜 readme.md        # Documentação principal do projeto
 ┣ 📜 requirements.txt # Lista de bibliotecas e dependências (marcadas por SO)
 ┗ 📜 ui.py            # Interface do usuário (PyQt6)
```

## 🚀 Como Iniciar

### Pré-requisitos

* Python 3.9 ou superior
* (Recomendado) Ambiente virtual (`venv` ou `conda`)

### Instalação

1. Clone o repositório para a sua máquina local:
   ```bash
   git clone https://github.com/seu-usuario/jarvis-code.git
   cd jarvis-code
   ```

2. Crie e ative um ambiente virtual:
   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate
   
   # Linux/MacOS
   python3 -m venv venv
   source venv/bin/activate
   ```

3. Instale as dependências. Você pode usar o arquivo de requirements:
   ```bash
   pip install -r requirements.txt
   ```
   *Ou instale o pacote em modo de edição usando o setup.py:*
   ```bash
   pip install -e .
   ```

4. Configure as variáveis de ambiente necessárias dentro da pasta `config/`.

### Execução

O projeto possui dois pontos de entrada principais, dependendo de como você deseja rodar:

* Para iniciar o **núcleo/backend** do Jarvis-Code em terminal:
  ```bash
  python main.py
  ```

* Para iniciar a **Interface de Usuário (UI)**:
  ```bash
  python ui.py
  ```

## 🛠️ Como Contribuir (Desenvolvedores)

O Jarvis-Code foi feito para crescer. Se você deseja adicionar novas funcionalidades:

1. **Ações:** Adicione novos scripts na pasta `actions/`.
2. **Plugins:** Utilize a estrutura de `plugins/` para criar novas habilidades.
3. **Provedores:** Crie conectores em `providers/` para novas APIs de IA.

Sinta-se livre para fazer um *Fork* do projeto, abrir *Issues* relatando bugs ou enviar um *Pull Request* com melhorias!

## 👨‍💻 Desenvolvedor

Desenvolvido por **Caio S.M.**

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
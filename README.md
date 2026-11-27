# 🧠 Jarvis-Code - Assistente Virtual Inteligente

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Status: Em Desenvolvimento](https://img.shields.io/badge/Status-Em%20Desenvolvimento-brightgreen.svg)
![Version](https://img.shields.io/badge/Version-1.2.0-informational.svg)

**Jarvis-Code** é um sistema de Inteligência Artificial modular, altamente customizável e expansível, desenvolvido totalmente em Python. Inspirado no icônico assistente virtual, este projeto foi desenhado para ser um núcleo de IA capaz de gerenciar memória, executar ações complexas, integrar-se com provedores externos de LLMs e oferecer uma interface de controle intuitiva.

## ✨ Funcionalidades Principais

* 🧩 **Arquitetura Modular:** Sistema construído de forma segmentada para facilitar a escalabilidade e a manutenção.
* 🔌 **Sistema de Plugins Avançado (Phase 2):**
  * **Descoberta Automática:** Plugins em `plugins/*.py` são carregados automaticamente no startup
  * **Hot-Reload:** Recarregamento automático ao salvar arquivos (requer `watchdog`)
  * **Sistema de Capacidades:** 14 permissões granulares (filesystem, network, system, UI, media, data, plugins)
  * **Execução Sandbox:** Isolamento em subprocesso com limites de tempo/memória
  * **Metadados Ricos:** version, author, license, homepage, repository, keywords, dependencies
  * **Preservação de Estado:** Estado do plugin mantido entre recarregamentos
  * **Gerenciador Visual:** UI para ativar/desativar, conceder capacidades, configurar sandbox
* 🧠 **Gerenciamento de Memória:** Capacidade de retenção de contexto, permitindo conversas fluidas e lembrança de interações passadas.
* 🌐 **Integração com Provedores:** Suporte facilitado para diferentes APIs e modelos de linguagem (OpenAI, Gemini, Ollama, etc.).
* ⚡ **Ações Customizadas:** Definição de fluxos de trabalho e comandos específicos que a IA pode executar no sistema operacional ou na web.
* 🖥️ **Interface Própria (`ui.py` e `dashboard`):** Interface visual e painel de controle para monitoramento, configuração e interação com o núcleo da IA.

## 📂 Estrutura do Projeto

Abaixo está o mapeamento exato da arquitetura do projeto:

```text
📦 jarvis-code
 ┣ 📂 actions/         # Scripts e funções de ações que a IA pode tomar
 ┣ 📂 config/          # Arquivos de configuração e variáveis de ambiente
 ┣ 📂 core/            # O cérebro do Jarvis-Code: orquestração e processamento
 ┣ 📂 dashboard/       # Arquivos do painel de monitoramento web/local
 ┣ 📂 memory/          # Módulos de persistência de dados e contexto
 ┣ 📂 plugins/         # Extensões para adicionar novas habilidades isoladas
 ┣ 📂 providers/       # Conectores para APIs externas de LLM e TTS/STT
 ┣ 📂 __pycache__/     # (Gerado automaticamente pelo Python, ignorar no git)
 ┣ 📜 LICENSE          # Termos de licença de uso do software
 ┣ 📜 main.py          # Ponto de entrada principal do núcleo da aplicação
 ┣ 📜 readme.md        # Documentação principal do projeto
 ┣ 📜 requirements.txt # Lista de bibliotecas e dependências
 ┣ 📜 setup.py         # Script para instalação e empacotamento do projeto
 ┗ 📜 ui.py            # Ponto de entrada focado na Interface de Usuário
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

## 🔌 Sistema de Plugins (Phase 2)

O Jarvis-Code possui um sistema de plugins avançado que permite estender a IA com novas capacidades de forma segura e controlada.

### Estrutura de um Plugin

Cada plugin é um arquivo `.py` na pasta `plugins/` (exceto arquivos iniciados com `_`). O arquivo deve conter:

1. **Dicionário `PLUGIN`** — Metadados obrigatórios
2. **Função `run(parameters, player, session_memory)`** — Lógica principal
3. **Opcional: `PLUGIN_SETTINGS`** — Schema de configuração para a UI

### Exemplo Mínimo

```python
# plugins/meu_plugin.py
PLUGIN = {
    "name": "meu_plugin",
    "version": "1.0.0",
    "author": "Seu Nome",
    "description": "Descrição que a IA usa para decidir quando chamar esta ferramenta.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "argumento": {"type": "STRING", "description": "O que este argumento faz"},
        },
        "required": ["argumento"],
    },
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    argumento = parameters.get("argumento", "")
    return f"Executou com {argumento}."
```

### Metadados Completos (Phase 2)

```python
PLUGIN = {
    "name": "meu_plugin",              # snake_case, único
    "version": "1.0.0",                # Semantic versioning
    "author": "Seu Nome",
    "license": "MIT",                  # SPDX identifier
    "homepage": "https://exemplo.com", # Documentação
    "repository": "https://github.com/user/repo",
    "keywords": ["tag1", "tag2"],      # Para descoberta
    "dependencies": ["requests"],      # Pacotes pip necessários
    "min_jarvis_version": "1.1.0",     # Versão mínima do Jarvis
    "description": "Descrição detalhada...",
    "parameters": {...},
    
    # Phase 2: Capabilities — Permissões declaradas
    "capabilities": [
        "filesystem.read",    # Ler arquivos
        "network.http",       # Requisições HTTP
        # ... veja lista completa abaixo
    ],
    
    # Phase 2: Sandbox — Execução isolada
    "sandboxed": False,             # true = roda em subprocesso isolado
    "sandbox_timeout": 30,          # Timeout em segundos
    "sandbox_memory_mb": 256,       # Limite de memória (Linux)
}
```

### Capacidades Disponíveis (14 no total)

| Grupo | Capacidades |
|-------|-------------|
| **Filesystem** | `filesystem.read`, `filesystem.write`, `filesystem.delete`, `filesystem.list` |
| **Network** | `network.http`, `network.websocket`, `network.raw` |
| **System** | `shell.exec`, `process.spawn`, `process.signal` |
| **UI/Input** | `ui.notify`, `ui.input`, `input.keyboard`, `input.mouse` |
| **Media** | `audio.record`, `audio.play`, `video.record` |
| **Data** | `memory.read`, `memory.write`, `config.read`, `config.write` |
| **Plugins** | `plugin.call`, `plugin.discover` |

**Importante:** O usuário deve conceder cada capacidade no **Plugin Manager** (UI) antes que o plugin possa executar. Capacidades não concedidas bloqueiam a execução.

### Sandbox (Execução Isolada)

Quando `"sandboxed": true`:
- O plugin roda em um **processo separado** (subprocess)
- Limites de **tempo** (`sandbox_timeout`) e **memória** (`sandbox_memory_mb`)
- Sem acesso direto à UI (`player` é `None`)
- Comunicação via JSON stdin/stdout
- Ideal para código não confiável ou que pode travar

### Hot-Reload

Com `watchdog` instalado (`pip install watchdog`):
- Salve o arquivo `.py` → plugin recarrega automaticamente
- Estado interno (`_state`) é **preservado** entre recarregamentos
- Capacidades concedidas são mantidas
- Contador de recarregamentos (`_reload_count`) incrementado

### Configuração por Plugin (PLUGIN_SETTINGS)

```python
PLUGIN_SETTINGS = {
    "namespace": "meu_plugin",      # Chave de configuração (padrão = name)
    "title": "Meu Plugin Config",   # Título na UI
    "fields": [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "secret",       # Oculta valor
            "default": "",
        },
        {
            "key": "modo",
            "label": "Modo de Operação",
            "type": "choice",
            "choices": ["rapido", "preciso"],
            "default": "rapido",
        },
        {
            "key": "ativo",
            "label": "Ativar Recurso X",
            "type": "boolean",
            "default": True,
        },
    ],
    "action": {                     # Botão de teste/conexão (opcional)
        "label": "Testar Conexão",
        "method": "test_connection",
    },
}
```

Acesse valores em `run()` via `config_manager.get_plugin_config("namespace")`.

### Plugins de Exemplo

- `system_info.py` — Info de CPU, memória, disco, rede (capabilities: filesystem.read, network.http)
- `safe_calc.py` — Calculadora sandboxada (sandboxed: true, 10s timeout, 64MB)
- `network_tools.py` — Requisições HTTP (capabilities: network.http, PLUGIN_SETTINGS)
- `text_processor.py` — Processamento de texto sandboxado (sandboxed, resource quotas, audit_log)
- `data_analyzer.py` — Análise de dados com plugin.call (usa safe_calc para cálculos)
- `lifecycle_demo.py` — Demonstra hooks de ciclo de vida (on_load, on_enable, on_disable, on_unload, on_reload)
- `plugin_caller.py` — Demonstra plugin.call capability

Copie `plugins/_template.py` para começar seu próprio plugin.

### Recursos Avançados do Phase 2

#### Quotas de Recursos
Plugins podem declarar limites de CPU, memória e disco que são aplicados em tempo de execução:
```python
"cpu_quota_percent": 50.0,    # Máximo 50% de CPU
"memory_quota_mb": 200,       # Máximo 200MB RAM
"disk_quota_mb": 100,         # Máximo 100MB disco
```

#### Auditoria (Audit Logging)
Habilite log de auditoria para compliance:
```python
"audit_log": True
```
Registra execuções bem-sucedidas e falhas com parâmetros, resultados e tempo.

#### Assinatura Criptográfica Ed25519
Para produção, use assinaturas Ed25519:
```python
# Assinar plugin
registry.sign_plugin_ed25519("meu_plugin", private_key_bytes, "Developer Name")

# Verificar assinatura
registry.verify_plugin_ed25519("meu_plugin", public_key_bytes)
```

#### Verificação de Atualizações
Verifique atualizações automáticas de plugins do GitHub:
```python
# Verificar um plugin
registry.check_plugin_updates("meu_plugin")

# Verificar todos
registry.check_all_plugin_updates()
```

#### Instalação Automática de Dependências
Instale dependências pip faltantes automaticamente:
```python
registry.install_plugin_dependencies("meu_plugin")
registry.install_all_missing_dependencies()
```

#### Presets de Capacidades
Aplique conjuntos predefinidos de capacidades:
```python
presets = registry.get_capability_presets()
# minimal, filesystem, network, system, media, data, full
registry.apply_capability_preset("meu_plugin", "network")
```

#### Agendamento (Cron-like)
Agende plugins para execução periódica:
```python
# Agendar execução horária
registry.schedule_plugin("meu_plugin", "0 * * * *", {"param": "value"})

# Ver agendamentos
registry.get_scheduled_plugins()

# Executar agendados (chamar periodicamente)
registry.run_scheduled_plugins(player, session_memory)
```

#### Perfilamento de Performance
Analise performance de plugins:
```python
profile = registry.profile_plugin("meu_plugin", {"param": "value"}, iterations=10)
# Retorna: min, max, mean, median, stdev, total_time
```

#### Exportação de Métricas (Prometheus)
Exporte métricas para monitoramento:
```python
metrics = registry.export_metrics_prometheus()
# Formato Prometheus text format
```

#### Snapshots e Rollback
Crie pontos de restauração de plugins:
```python
# Criar snapshot
registry.create_plugin_snapshot("meu_plugin")

# Listar snapshots
registry.list_plugin_snapshots("meu_plugin")

# Rollback para snapshot anterior
registry.rollback_plugin("meu_plugin", -1)  # -1 = mais recente
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
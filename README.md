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

#### Níveis de Confiança (Trust Levels)
Configure níveis de confiança para plugins:
```python
# Trust levels: official, community, untrusted, blocked
registry.set_plugin_trust_level("meu_plugin", "community")

# Ver nível de confiança
registry.get_plugin_trust_level("meu_plugin")

# Info detalhada
registry.get_trust_level_info("meu_plugin")
```

#### Assinatura Criptográfica Avançada
```python
# Ed25519 (recomendado para produção)
registry.sign_plugin_ed25519("meu_plugin", private_key_bytes, "Developer")
registry.verify_plugin_ed25519("meu_plugin", public_key_bytes)

# RSA PKCS#1 v1.5
registry.sign_plugin_rsa("meu_plugin", private_key_pem, "Developer")
registry.verify_plugin_rsa("meu_plugin", public_key_pem)
```

#### Sandbox com cgroups (Linux)
```python
# Isolamento real de memória/CPU usando cgroups v2
# Configurado automaticamente se disponível no sistema
"sandboxed": true,
"sandbox_memory_mb": 256,
"cpu_quota_percent": 50.0,
```

#### Marketplace de Plugins
```python
# Buscar plugins online (GitHub)
registry.search_plugins_online("weather")

# Instalar plugin de URL
registry.install_plugin_from_url("https://raw.githubusercontent.com/user/repo/main/plugin.py")
```

#### Resolução de Dependências
```python
# Resolver dependências transitivas
registry.resolve_plugin_dependencies("meu_plugin")

# Ver grafo completo de dependências
registry.get_dependency_graph()

# Detectar dependências circulares
registry.check_circular_dependencies()
```

#### Orçamentos de Performance
```python
# Definir orçamento
registry.set_performance_budget("meu_plugin", {
    "max_avg_time_ms": 5000,
    "max_memory_mb": 200,
    "min_success_rate": 95.0,
})

# Verificar orçamento
registry.check_performance_budget("meu_plugin")
registry.check_all_performance_budgets()
```

#### Replay de Eventos / Debugging
```python
# Gravar eventos
registry.record_plugin_event("meu_plugin", "run_start", {"parameters": {...}})

# Ver log de eventos
registry.get_plugin_event_log("meu_plugin", "run_error", limit=50)

# Replay de execuções
registry.replay_plugin_events("meu_plugin", player, session_memory)
```

#### Testes A/B
```python
# Criar teste A/B
registry.create_ab_test("meu_plugin",
    variant_a={"algorithm": "v1", "threshold": 0.5},
    variant_b={"algorithm": "v2", "threshold": 0.7},
    traffic_split=0.5
)

# Determinar variante para execução atual
variant = registry.get_ab_test_variant("meu_plugin")

# Registrar resultado
registry.record_ab_test_result("meu_plugin", variant, success=True)

# Ver resultados com significância estatística
registry.get_ab_test_results("meu_plugin")
```

#### Webhooks
```python
# Registrar webhook
registry.register_webhook("meu_plugin", "plugin_error",
    "https://meuservidor.com/webhook", secret="chave-secreta")

# Listar webhooks
registry.get_webhooks("meu_plugin")

# Remover webhook
registry.unregister_webhook("meu_plugin", "https://meuservidor.com/webhook")
```

#### Streaming de Métricas em Tempo Real
```python
# Iniciar stream
registry.start_metrics_stream("meu_plugin", interval=10.0)

# Parar stream
registry.stop_metrics_stream("meu_plugin")

# Consumir via hook
registry.register_hook("metrics_stream", callback_fn)
```

#### Validação de Configuração
```python
# Validar config contra schema PLUGIN_SETTINGS
registry.validate_plugin_config("meu_plugin", config)

# Obter config validada
registry.get_validated_config("meu_plugin")
```

#### Listas de Controle de Acesso (ACLs)
```python
# Definir ACL
registry.set_plugin_acl("meu_plugin", {
    "allow_users": ["user1", "user2"],
    "deny_users": ["blocked_user"],
    "allow_roles": ["premium", "admin"],
    "deny_roles": ["guest"],
    "allow_ips": ["192.168.1.0/24"],
    "time_restrictions": {
        "allowed_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17],
        "allowed_days": [0, 1, 2, 3, 4],  # Mon-Fri
    }
})

# Verificar acesso
registry.check_plugin_acl("meu_plugin", user_id="user1", roles=["premium"], ip="192.168.1.100")
```

#### Análise de Uso
```python
# Analytics de um plugin (últimos 30 dias)
registry.get_usage_analytics("meu_plugin", days=30)

# Analytics de todos os plugins
registry.get_all_usage_analytics(days=30)
```

#### Internacionalização (i18n)
```python
# Traduções no plugin (TRANSLATIONS dict)
# Obter traduções para locale
registry.get_plugin_translations("meu_plugin", "pt")

# Definir locale preferido
registry.set_plugin_locale("meu_plugin", "es")
registry.get_plugin_locale("meu_plugin")
```

#### Rastreamento de Custos (API)
```python
# Registrar custo de chamada API
registry.record_plugin_cost("meu_plugin", 0.0001, "USD", {"model": "gpt-4"})

# Ver custos
registry.get_plugin_costs("meu_plugin", days=30)
registry.get_all_plugin_costs(days=30)
```

#### Health Checks com Alertas
```python
# Health check completo
registry.run_health_check("meu_plugin")

# Health checks de todos os plugins
registry.run_all_health_checks()
# Retorna: overall_status (healthy/degraded/critical), checks, alerts
```

#### Migração de Configuração
```python
# Migrar config entre versões
registry.migrate_plugin_config("meu_plugin", "1.0.0", "2.0.0", {
    "1.0.0": "migrate_v1_to_v2",
    "2.0.0": "migrate_v2_to_v3",
})

# Plugin deve definir funções de migração:
# def migrate_v1_to_v2(config): return new_config
```

#### Backup e Restore
```python
# Backup completo
backup = registry.backup_plugin("meu_plugin", include_source=True)

# Restore
registry.restore_plugin_backup("meu_plugin", backup)
```

#### Changelog e Comparação de Versões
```python
# Obter changelog
registry.get_plugin_changelog("meu_plugin")

# Comparar versões
registry.compare_plugin_versions("meu_plugin", "1.0.0", "2.0.0")
```

#### Marketplace com Avaliações
```python
# Avaliar plugin
registry.submit_plugin_rating("meu_plugin", 5, "Excelente!", "user123")

# Ver avaliações
registry.get_plugin_ratings("meu_plugin")

# Marketplace completo
registry.get_marketplace_plugins()
```

#### Notificações de Atualização
```python
# Verificar atualizações com notificação
registry.check_for_updates_with_notification("meu_plugin")

# Verificar todas
registry.check_all_updates_notify()
```

### Novos Plugins de Exemplo (Phase 2 Avançado)

- `weather_service.py` — API weather com cost tracking, i18n (en/pt/es), webhooks, health checks, migrações
- `smart_recommendations.py` — Recomendações com A/B testing, ACLs, collaborative filtering
- `scheduled_monitor.py` — Monitoramento agendado (cron), metrics streaming, health checks
- `network_tools.py` — Requisições HTTP com PLUGIN_SETTINGS
- `text_processor.py` — Processamento sandboxado com resource quotas e audit_log
- `data_analyzer.py` — Análise de dados com plugin.call capability
- `lifecycle_demo.py` — Demonstra todos os 5 hooks de ciclo de vida
- `plugin_caller.py` — Demonstra plugin.call capability

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
# 🧠 Jarvis-Code - Assistente Virtual Inteligente

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
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
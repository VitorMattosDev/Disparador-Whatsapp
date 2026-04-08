# 📲 Disparador de Mensagens — WhatsApp Web

Ferramenta desktop para envio automatizado de mensagens via WhatsApp Web, com múltiplas estratégias anti-bloqueio integradas. Desenvolvida para uso interno da equipe de vendas da **Genesys Fibra**.

---

## 📋 Funcionalidades

- **Disparo em massa** a partir de uma lista de números colada diretamente na interface
- **5 variações de mensagem** — uma é sorteada aleatoriamente para cada contato, quebrando o padrão de spam
- **Personalização por nome** com `{nome}` na mensagem
- **Sessão salva do Chrome** — escaneia o QR Code apenas na primeira vez
- **Delay aleatório** entre mensagens configurável (mín/máx em segundos)
- **Pausa longa** automática a cada N envios para simular comportamento humano
- **Lista Negra permanente** — números bloqueados manualmente que nunca receberão mensagens
- **Lista de Recentes** — números do mês anterior que são pulados automaticamente, com substituição mensal
- **Comentar números** com `#` na lista para ignorar pontualmente sem apagar
- Log em tempo real com barra de progresso
- Botão de cancelamento a qualquer momento

---

## 🛡️ Estratégias Anti-Bloqueio

| Estratégia | Descrição |
|---|---|
| Sessão persistente | Chrome salva o login do WhatsApp Web entre execuções |
| Delay aleatório | Intervalo variável entre mensagens (padrão: 35–100s) |
| Pausa longa | Para por X minutos a cada N envios (padrão: 5min a cada 15) |
| Múltiplas variações | Cada contato recebe uma mensagem diferente sorteada |
| Zero-width space | Caractere invisível inserido em posição aleatória — mensagens idênticas ficam tecnicamente distintas para os filtros |
| Inserção via clipboard | Texto inserido via `execCommand` em vez de digitação caractere por caractere — evita timeout em mensagens longas |

> ⚠️ **Recomendação:** limite o disparo a ~50 números por dia por número de WhatsApp. Listas maiores devem ser divididas em sessões.

---

## 🖥️ Requisitos

- Windows 10/11
- Python 3.11 (recomendado — evitar 3.13+)
- Google Chrome ou Microsoft Edge instalado
- Selenium 4.6+ (gerencia o ChromeDriver automaticamente)

---

## ⚙️ Instalação e Execução

### 1. Clonar o repositório

```bash
git clone https://github.com/VitorMattosDev/Disparador-Whatsapp.git
cd Disparador-Whatsapp
```

### 2. Criar ambiente virtual com Python 3.11

```bash
C:\Python311\python.exe -m venv C:\venv_disparador
C:\venv_disparador\Scripts\Activate.ps1
```

### 3. Instalar dependências

```bash
pip install selenium customtkinter
```

### 4. Executar

```bash
python disparador_whatsapp.py
```

---

## 📦 Gerar Executável (.exe)

Para distribuir para usuários sem Python instalado:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --collect-all selenium --collect-all customtkinter --name "DisparadorWhatsApp" disparador_whatsapp.py
```

O `.exe` será gerado em `dist/DisparadorWhatsApp.exe`.

> **Atenção:** os arquivos `numeros_bloqueados.txt` e `numeros_recentes.txt` devem ficar na **mesma pasta** do `.exe` para que a persistência funcione corretamente.

---

## 🚀 Como Usar

### Preparando a lista de números

Cole os números na caixa **Lista de Números**, um por linha. Formatos aceitos:

```
17999998888
(17) 99999-8888
55 17 99999-8888
17999998888;João        ← com nome para personalização
# 17988887777           ← comentado com # será ignorado nessa execução
```

### Configurando as mensagens

O painel **Variações de Mensagem** possui 5 abas. Preencha quantas quiser — abas vazias são ignoradas. Use `{nome}` para inserir o nome do contato:

```
Olá, {nome}! 👋

Aqui é da Genesys Fibra. Posso te apresentar nossos planos?
```

### Configurações anti-bloqueio

| Campo | Padrão | Descrição |
|---|---|---|
| Intervalo mínimo | 35s | Menor tempo de espera entre mensagens |
| Intervalo máximo | 100s | Maior tempo de espera entre mensagens |
| Pausa a cada | 15 envios | Frequência da pausa longa |
| Duração da pausa | 5 min | Duração da pausa longa (0 = desativar) |

### Iniciando o disparo

1. Clique em **▶ Iniciar Disparo**
2. Confirme a janela de resumo
3. O Chrome abrirá o WhatsApp Web — escaneie o QR Code se necessário
4. O disparo começa automaticamente
5. Acompanhe o progresso no log

---

## 🚫 Lista Negra

Números adicionados à lista negra **nunca** receberão mensagens, independentemente de aparecerem em listas futuras.

**Adicionar:** abra o painel *🚫 Lista Negra*, digite o número e clique em **Bloquear número**.

**Remover:** clique em **✕ Desbloquear** ao lado do número.

Persistência: salvo em `numeros_bloqueados.txt` na pasta do programa.

---

## ⏭️ Lista de Recentes (Controle Mensal)

Evita que números chamados no mês anterior sejam disparados novamente quando reaparecerem na lista do mês atual.

### Fluxo mensal

**Início do mês (ex: começando Março, tendo rodado Fevereiro):**
1. Abra o painel *⏭️ Números Recentes*
2. Cole a lista de números de Fevereiro na caixa de texto
3. Clique em **💾 Substituir pela lista abaixo**
4. Rode normalmente os números de Março — os de Fevereiro serão pulados automaticamente

**Virada para o próximo mês (começando Abril):**
1. Cole os números de Março na caixa de texto
2. Clique em **💾 Substituir** — Fevereiro sai, Março entra
3. Abril rodará pulando Março, e Fevereiro volta a ser elegível

> A lista aceita os mesmos formatos da lista principal, incluindo `número;nome`.

Persistência: salvo em `numeros_recentes.txt` na pasta do programa.

---

## 📁 Arquivos Gerados

| Arquivo | Local | Descrição |
|---|---|---|
| `numeros_bloqueados.txt` | Pasta do programa | Lista negra permanente |
| `numeros_recentes.txt` | Pasta do programa | Números do mês anterior |
| `.wpp_disparador_profile/` | `C:\Users\<usuario>\` | Perfil do Chrome com sessão do WhatsApp salva |

---

## 📝 Log de Saída

| Ícone | Significado |
|---|---|
| 📤 | Tentando enviar para o número |
| ✅ | Mensagem enviada com sucesso |
| ❌ | Número não encontrado no WhatsApp |
| ⚠️ | Número inválido ou com colunas insuficientes |
| 🚫 | Número na lista negra — pulado |
| ⏭️ | Número na lista de recentes — pulado |
| ⏳ | Aguardando delay entre mensagens |
| ☕ | Pausa longa em andamento |
| ⛔ | Disparo cancelado pelo usuário |

---

## 🔧 Estrutura do Código

```
disparador_whatsapp.py
│
├── Constantes e configurações
│   ├── BASE_DIR, CHROME_PROFILE_DIR
│   ├── BLACKLIST_FILE, RECENTES_FILE
│   └── MENSAGENS_PADRAO
│
├── Persistência
│   ├── carregar_blacklist / salvar_blacklist / adicionar_blacklist / remover_blacklist
│   └── carregar_recentes / salvar_recentes
│
├── Helpers
│   ├── limpar_numero()       — normaliza e adiciona DDI +55
│   └── variar_mensagem()     — insere zero-width space aleatório
│
├── Selenium
│   ├── iniciar_driver()      — Chrome com perfil persistente, Edge como fallback
│   ├── aguardar_login()      — detecta login por múltiplos seletores CSS
│   ├── encontrar_caixa()     — localiza caixa de texto por múltiplos seletores
│   └── enviar_mensagem()     — injeta texto via execCommand e envia
│
├── Thread principal
│   └── disparar()            — loop de envio com skip de blacklist/recentes,
│                               delays e pausas longas
│
└── Interface (App — CTk)
    ├── _build_ui()                — painel de números, mensagens, config e log
    ├── _build_blacklist_panel()   — painel recolhível da lista negra
    ├── _build_recentes_panel()    — painel recolhível de números recentes
    └── _poll()                    — atualiza UI com eventos da thread de disparo
```

---

## ⚠️ Aviso Legal

Esta ferramenta foi desenvolvida para uso com leads que forneceram consentimento explícito ao se conectar à rede Wi-Fi da Genesys Fibra, aceitando os termos de uso que incluem contato comercial posterior. O uso desta ferramenta para envio de mensagens não solicitadas pode violar os Termos de Serviço do WhatsApp e legislações aplicáveis (LGPD, Marco Civil da Internet). Use com responsabilidade.

---

## 📄 Licença

MIT License — veja o arquivo `LICENSE` para detalhes.

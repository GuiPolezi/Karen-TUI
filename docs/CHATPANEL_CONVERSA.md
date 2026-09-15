# ChatPanel: leitura de conversa (Fase 6.3) — medição de 15/09/2026

Ferramenta: `scripts/chatpanel_diag_open.py <numero>` (TUI fechada, usuário dedicado,
socket instrumentado). Conversa de teste: o celular do técnico, atribuída a outro atendente.

## Como o painel carrega uma conversa

- `changeTheInfo(el, numero)` (chat.js): marca o `li` como ativo, faz
  **`POST inc_chat_view.php {number}`** e injeta o HTML em `#main-chat-content`; define
  `#chat_number` e foca o textarea. Não chama `control.php` no cliente.
- O app **não** chama `changeTheInfo`: faz só o `POST inc_chat_view.php` dentro da página
  (mesma técnica da ressincronização) e lê a resposta. A lista e o chat "aberto" do painel
  não mudam.

## Efeitos colaterais medidos (14:48, sessão do usuário dedicado "User CMD")

| Pergunta | Resultado |
|---|---|
| A resposta traz as mensagens? | Sim: 134 KB, `#main-chat-content` com 51 itens (43 mensagens, 7 marcos de dia, 1 "ver mais") |
| O servidor marca como lida? | **Não.** 30 s depois, `control-atende-on-ot.php` ainda listava a conversa com 1 não lida |
| Evento de socket para a conversa? | **Nenhum.** Só chegaram `refreshRead` de outros números (outras pessoas lendo os próprios chats) |
| DOM local mudou? | Não (o badge da lista continuou em 1, nada ficou "ativo") |
| Badge sumiu no navegador do técnico? | _pendente de confirmação do técnico_ |
| "Visto" no celular do contato? | _pendente de confirmação do técnico_ |

Conclusão preliminar: ler a conversa por `inc_chat_view.php` na sessão do usuário
dedicado é **somente leitura** do ponto de vista do servidor (nenhuma marcação de lida,
nenhum evento). Se o técnico confirmar que o badge e o "visto" não mudaram, a Feature D
(7.2) é implementada; caso contrário, a leitura é descartada e fica o detalhe só com os
dados da lista + `o` para abrir no navegador.

## Estrutura da resposta (base de `tests/fixtures/chatpanel_conversation.html`)

- `#main-chat-content > ul > li`:
  - `li.chat-item-start` — mensagem do contato: autor em `span.chatnameperson`, hora em
    `span.msg-sent-time` (`dd/mm/aaaa HH:MM`), texto em `.main-chat-msg p` (pode ter `<br>`).
  - `li.chat-item-end` — mensagem do técnico: sem autor no item; hora e texto iguais.
  - `li.chat-day-label` — marco ("Atendimento iniciado/finalizado em …").
  - `li#but-seemore` — link "ver mais" (mensagens antigas via `inc_chat_viewmore.php`);
    não é seguido pelo app.
- Cabeçalho `.main-chat-head`: nome, número e avatar do contato.
- Mídias (imagem/áudio/arquivo) não apareceram na amostra; o parser descreve qualquer
  `img`/`audio`/`video`/link de download como `[imagem]`, `[áudio]`, `[vídeo]`, `[arquivo]`.

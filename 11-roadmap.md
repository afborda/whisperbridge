# 11 — Roadmap

Fases futuras após o MVP Windows funcionar.

---

## Status atual — MVP Windows

```
✅ Análise de hardware
⬜ Ambiente configurado
⬜ Captura WASAPI funcionando
⬜ VAD identificando fala
⬜ Transcrição no terminal
⬜ Tradução no terminal
⬜ Pipeline completo com parciais
⬜ WebSocket server rodando
⬜ Overlay React aparecendo
⬜ Build e instalador gerados
```

---

## Fase 5 — Melhorias do app Windows

Após o MVP básico funcionar:

- [ ] Seletor de dispositivo de áudio na interface
- [ ] Seletor de modelo Whisper (small / medium / large)
- [ ] Tamanho e posição da legenda salvos
- [ ] Histórico de reunião exportável
- [ ] Glossário editável pela interface
- [ ] Modo privacidade (não salva nada)
- [ ] Indicador de latência visível
- [ ] Atalhos configuráveis pelo usuário
- [ ] Atualização automática

---

## Fase 6 — Suporte a macOS

### Captura de áudio

No macOS, não existe equivalente nativo ao WASAPI Loopback. Opções:

| Solução | Custo | Complexidade | Qualidade |
|---|---|---|---|
| BlackHole (driver virtual) | gratuito | usuário configura manualmente | boa |
| Loopback (Rogue Amoeba) | ~US$99 | plug and play | excelente |
| ScreenCaptureKit (macOS 13+) | nativo | integração código | boa |

Para o primeiro MVP macOS, usar **BlackHole**:
1. Usuário instala BlackHole 2ch
2. Cria Multi-Output Device no Audio MIDI Setup
3. WhisperBridge detecta automaticamente

Para versão polida, migrar para **ScreenCaptureKit** — a Apple abriu API nativa para captura de áudio de apps específicos no macOS 13+.

### Distribuição macOS

```powershell
# Build para macOS (rodar em Mac)
npm run tauri build -- --target universal-apple-darwin
```

Gera `.dmg` com suporte a Intel e Apple Silicon.

Requer:
- Conta Apple Developer (~US$99/ano) para notarização
- Assinatura do bundle para funcionar no macOS 14+

---

## Fase 7 — Múltiplos idiomas

Adicionar suporte a outros pares de idiomas:

| Par | Modelo sugerido |
|---|---|
| Inglês → Português | Helsinki opus-mt-tc-big-en-pt (atual) |
| Espanhol → Português | Helsinki opus-mt-es-pt |
| Francês → Português | Helsinki opus-mt-fr-pt |
| Qualquer → qualquer | NLLB-200 (~600 MB, 200 idiomas) |

O Whisper multilíngue (sem `.en`) detecta o idioma automaticamente quando `language=None`.

---

## Fase 8 — Identificação de falantes

Distinguir quem está falando em reuniões com vários participantes:

- **pyannote.audio** — diarização de falantes (requer licença HuggingFace)
- Identificar automaticamente "Pessoa A", "Pessoa B"
- Mostrar na legenda: `[John] We need to check the pipeline`

Complexidade: alta. Deixar para depois da versão 1.0 estável.

---

## Fase 9 — Web + SaaS

### Painel web (conta e configurações)

```
whisperbridge.app
    ├── /dashboard      → histórico de reuniões
    ├── /glossary       → editar glossário
    ├── /settings       → preferências sincronizadas
    ├── /models         → gerenciar modelos instalados
    └── /account        → plano e cobrança
```

### Modelo de negócio sugerido

| Plano | Preço | Limite |
|---|---|---|
| Gratuito | R$ 0 | uso local ilimitado, 1 dispositivo |
| Pro | R$ 29/mês | múltiplos dispositivos, sincronização, suporte |
| Team | R$ 79/mês | glossário compartilhado, histórico de equipe |

O motor de IA continua rodando localmente — o SaaS monetiza conveniência, não processamento.

### Opção cloud (API paga por minuto)

Para usuários sem GPU, oferecer backend em nuvem:

```
WhisperBridge app
    │
    ├── GPU local disponível → roda local (gratuito)
    └── Sem GPU → usa API cloud (cobrado por hora de reunião)
```

Isso abre o mercado para quem tem apenas notebook com CPU.

---

## Fase 10 — Extensão de navegador

Para reuniões no Teams Web, Meet e Zoom Web sem instalar o app desktop:

- Extensão Chrome/Edge que injeta o overlay na página da reunião
- Captura o áudio da aba via `getDisplayMedia`
- Envia para o engine local via WebSocket
- Funciona como fallback quando não há app instalado

---

## Marcos de versão

| Versão | O que entrega |
|---|---|
| 0.1 | Terminal: captura + transcrição funcionando |
| 0.2 | Terminal: tradução adicionada |
| 0.3 | Overlay básico funcionando sobre o Teams |
| 0.4 | App instalável, atalhos, configurações |
| 0.5 | Build estável, glossário, histórico |
| 1.0 | Release público Windows |
| 1.5 | Suporte macOS |
| 2.0 | Múltiplos idiomas + web |

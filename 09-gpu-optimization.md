# 09 — Otimização de GPU

Configurações para extrair o máximo da RTX 4060 Ti e usar a Intel UHD 770 para liberar VRAM.

---

## 9.1 Forçar Intel UHD para renderização do Windows

No Windows 11, é possível definir qual GPU cada aplicativo usa.

**Configurações → Sistema → Vídeo → Configurações de gráficos**

Adicionar manualmente e definir para "Economia de energia" (Intel):
- Microsoft Teams
- Brave / Edge / Chrome
- Discord
- Spotify
- Windows Explorer

Definir para "Alto desempenho" (NVIDIA):
- O executável do WhisperBridge (quando gerado)

Assim a NVIDIA para de renderizar a interface do Windows e fica livre para o pipeline de IA.

**Ganho estimado:** libera 400–600 MiB de VRAM que estavam sendo usados por apps de interface.

---

## 9.2 Configuração do faster-whisper para máxima performance

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    "medium.en",
    device="cuda",
    compute_type="float16",       # float16 na RTX 4060 Ti é ideal
    num_workers=2,                # paralelismo interno
    cpu_threads=4,                # threads CPU para pré-processamento
    download_root="./models",
)
```

**Tabela de compute_type:**

| Tipo | VRAM | Velocidade | Qualidade |
|---|---|---|---|
| float32 | alta | lento | referência |
| float16 | ~50% | 2x mais rápido | igual |
| int8_float16 | ~35% | 3x mais rápido | quase igual |
| int8 | ~30% | 3x mais rápido | boa |

Para reuniões, `float16` é o melhor equilíbrio. `int8_float16` pode ser útil se quiser rodar `large-v3` com menos VRAM.

---

## 9.3 Comparativo de modelos no seu hardware

| Modelo | VRAM | Latência 5s áudio | Qualidade |
|---|---|---|---|
| small.en float16 | ~970 MB | ~200–350 ms | boa |
| medium.en float16 | ~2.5 GB | ~500–800 ms | ótima |
| distil-large-v3 float16 | ~1.5 GB | ~400–600 ms | muito boa |
| large-v3 float16 | ~3.1 GB | ~900–1400 ms | excelente |
| large-v3 int8_float16 | ~2.1 GB | ~600–900 ms | excelente |

**Recomendação inicial:** `medium.en float16`
**Se quiser qualidade máxima:** `large-v3 int8_float16`

---

## 9.4 Uso total de VRAM por cenário

### Cenário padrão (medium.en)
```
Sistema + interface (Intel assumiu parte)  ~1.5 GB
Whisper medium.en                          ~2.5 GB
Helsinki EN→PT                             ~300 MB
Silero VAD                                  ~50 MB
─────────────────────────────────────────────────
Total                                      ~4.4 GB
Livre                                      ~3.8 GB
```

### Cenário máximo (large-v3 int8_float16)
```
Sistema + interface                        ~1.5 GB
Whisper large-v3 int8_float16              ~2.1 GB
Helsinki EN→PT                             ~300 MB
Silero VAD                                  ~50 MB
─────────────────────────────────────────────────
Total                                      ~4.0 GB
Livre                                      ~4.2 GB
```

Ambos cabem com folga.

---

## 9.5 Evitar fragmentação de VRAM

```python
import torch

# Antes de carregar os modelos
torch.cuda.empty_cache()

# Configurar alocador para reduzir fragmentação
import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
```

---

## 9.6 Monitorar uso em tempo real

```python
# Adicionar ao servidor para logar uso de VRAM a cada 30s

import torch
import threading
import time

def monitor_vram():
    while True:
        if torch.cuda.is_available():
            used = torch.cuda.memory_allocated() / 1024**3
            reserved = torch.cuda.memory_reserved() / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            print(f"[VRAM] used={used:.2f}GB reserved={reserved:.2f}GB total={total:.2f}GB")
        time.sleep(30)

threading.Thread(target=monitor_vram, daemon=True).start()
```

---

## 9.7 Configuração de energia no Windows

Para garantir que a NVIDIA opere em desempenho máximo durante reuniões:

**Painel de controle NVIDIA → Gerenciar configurações 3D → Global:**
- Modo de gerenciamento de energia: `Preferir desempenho máximo`
- Desligar após: `Nunca` (enquanto o app estiver rodando)

Ou via PowerShell:

```powershell
# Ver perfil atual
nvidia-smi -q -d PERFORMANCE

# Definir para desempenho máximo (requer admin)
nvidia-smi --auto-boost-default=0
nvidia-smi -pm 1
```

---

## 9.8 Checklist de otimização

- [ ] Intel UHD definida como GPU padrão para Teams, browser, Discord
- [ ] NVIDIA definida como GPU padrão para WhisperBridge
- [ ] `compute_type="float16"` no faster-whisper
- [ ] `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` no ambiente
- [ ] Modo de energia NVIDIA em alto desempenho
- [ ] Monitor de VRAM ativo em desenvolvimento

---

**Próximo passo:** [10-packaging.md](./10-packaging.md)

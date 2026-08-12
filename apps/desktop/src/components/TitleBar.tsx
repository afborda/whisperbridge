import { useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  ConnectionStatus, CostState, ProfileState, UserSettings,
} from "../hooks/useTranslationSocket";
import { ProfilePicker } from "./ProfilePicker";
import { SettingsPanel } from "./SettingsPanel";
import { ENGINE_HTTP } from "../config";

// O mesmo bundle roda dentro do Tauri e num navegador comum (modo sem Rust).
// getCurrentWindow() depende do IPC do Tauri e estoura no navegador, então os
// botões de janela só aparecem onde existe janela para controlar.
const IS_TAURI =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

async function closeAndShutdown() {
  // keepalive: o POST precisa sair mesmo com a janela já fechando, senão o
  // Python fica com Whisper+tradutor na VRAM e a memória não volta.
  try {
    await fetch(`${ENGINE_HTTP}/shutdown`, { method: "POST", keepalive: true });
  } catch {
    /* engine já morto */
  }
  try {
    await getCurrentWindow().close();
  } catch {
    /* não é Tauri */
  }
}

const STATUS_DOT: Record<ConnectionStatus, string> = {
  connected:    "#4ade80",
  connecting:   "#fbbf24",
  disconnected: "#f87171",
  error:        "#f87171",
};
const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connected:    "conectado",
  connecting:   "conectando...",
  disconnected: "desconectado",
  error:        "erro de conexão",
};

interface Props {
  connStatus: ConnectionStatus;
  isRunning: boolean;
  device: string;
  segCount: number;
  onStart: () => void;
  onPause: () => void;
  onClear: () => void;
  profileState: ProfileState;
  switching: boolean;
  profileError: string | null;
  onSetProfile: (id: string) => void;
  cost: CostState;
  settings: UserSettings | null;
  onSaveSettings: (payload: Record<string, string>) => void;
}

export function TitleBar({
  connStatus, isRunning, device, segCount, onStart, onPause, onClear,
  profileState, switching, profileError, onSetProfile, cost,
  settings, onSaveSettings,
}: Props) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const deviceShort = device
    .replace(" [Loopback]", "")
    .replace("Alto-falantes ", "")
    .replace("(", "")
    .replace(")", "");
  const connected = connStatus === "connected";

  return (
    <>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "7px 10px 6px",
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        flexShrink: 0,
        userSelect: "none",
      }}
    >
      {/* dot */}
      <div style={{
        width: 8, height: 8,
        borderRadius: "50%",
        background: STATUS_DOT[connStatus],
        boxShadow: `0 0 7px ${STATUS_DOT[connStatus]}`,
        flexShrink: 0,
        transition: "background 0.3s",
      }} />

      {/* área de drag — ocupa o espaço entre dot e botões */}
      <div
        data-tauri-drag-region
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          gap: 8,
          cursor: "move",
          height: "100%",
          minWidth: 0,
        }}
      >
        <span style={{
          color: "rgba(255,255,255,0.60)",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.07em",
          textTransform: "uppercase",
          flexShrink: 0,
          pointerEvents: "none",
        }}>
          WhisperBridge
        </span>
        <span style={{
          color: "rgba(255,255,255,0.28)",
          fontSize: 11,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          pointerEvents: "none",
        }}>
          {connected && device ? `· ${deviceShort}` : `· ${STATUS_LABEL[connStatus]}`}
        </span>
        {segCount > 0 && (
          <span style={{
            color: "rgba(255,255,255,0.20)",
            fontSize: 11,
            flexShrink: 0,
            pointerEvents: "none",
          }}>
            {segCount} frases
          </span>
        )}
        {cost.calls > 0 && (
          <span
            title={
              `${cost.model ?? "nuvem"}\n` +
              `${cost.calls} chamadas\n` +
              `${cost.tokensIn.toLocaleString("pt-BR")} tokens de entrada\n` +
              `${cost.tokensOut.toLocaleString("pt-BR")} tokens de saída` +
              (cost.priced ? "" : "\n\nPreço deste modelo não está na tabela do servidor.")
            }
            style={{
              color: "rgba(96,165,250,0.55)",
              fontSize: 11,
              flexShrink: 0,
              fontVariantNumeric: "tabular-nums",
              pointerEvents: "auto",
              cursor: "help",
            }}
          >
            {cost.priced
              ? `US$ ${cost.usd.toFixed(4).replace(".", ",")}`
              : `${((cost.tokensIn + cost.tokensOut) / 1000).toFixed(1)}k tokens`}
          </span>
        )}
      </div>

      {/* ações */}
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexShrink: 0 }}>
        <ProfilePicker
          state={profileState}
          switching={switching}
          error={profileError}
          onSelect={onSetProfile}
          onOpenIaSetup={() => setSettingsOpen(true)}
        />
        <button
          title="Idiomas e chave da IA"
          onClick={() => setSettingsOpen(true)}
          style={{
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.10)",
            borderRadius: 6,
            color: "#e2e8f0",
            padding: "3px 8px",
            font: "500 11px system-ui, sans-serif",
            cursor: "pointer",
          }}
        >
          ⚙
        </button>
        {connected && !isRunning && (
          <Btn onClick={onStart} bg="#2563eb" label="▶  Iniciar" />
        )}
        {connected && isRunning && (
          <Btn onClick={onPause} bg="#d97706" label="⏸  Pausar" />
        )}
        {segCount > 0 && (
          <Btn onClick={onClear} bg="rgba(255,255,255,0.10)" label="Limpar" />
        )}
      </div>

      {/* janela — só no Tauri; no navegador quem fecha é a aba */}
      {IS_TAURI && (
        <div style={{ display: "flex", gap: 3, marginLeft: 8, flexShrink: 0 }}>
          <WinBtn onClick={() => getCurrentWindow().minimize()} label="−" hover="rgba(255,255,255,0.14)" />
          <WinBtn onClick={closeAndShutdown}   label="✕" hover="#dc2626" />
        </div>
      )}
    </div>
    <SettingsPanel
      open={settingsOpen}
      settings={settings}
      cloud={profileState.cloud}
      saving={false}
      onClose={() => setSettingsOpen(false)}
      onSave={(payload) => {
        onSaveSettings(payload);
        setSettingsOpen(false);
      }}
    />
    </>
  );
}

function Btn({ onClick, bg, label }: { onClick: () => void; bg: string; label: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: bg,
        color: "#fff",
        border: "none",
        borderRadius: 5,
        padding: "3px 12px",
        fontSize: 12,
        fontFamily: "inherit",
        fontWeight: 600,
        cursor: "pointer",
        letterSpacing: "0.02em",
        transition: "filter 0.15s",
        whiteSpace: "nowrap",
      }}
      onMouseEnter={e => (e.currentTarget.style.filter = "brightness(1.2)")}
      onMouseLeave={e => (e.currentTarget.style.filter = "")}
    >
      {label}
    </button>
  );
}

function WinBtn({ onClick, label, hover }: { onClick: () => void; label: string; hover: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: "transparent",
        color: "rgba(255,255,255,0.40)",
        border: "none",
        borderRadius: 4,
        width: 24,
        height: 22,
        fontSize: 13,
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        transition: "background 0.15s, color 0.15s",
        padding: 0,
        fontFamily: "inherit",
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = hover;
        e.currentTarget.style.color = "#fff";
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.color = "rgba(255,255,255,0.40)";
      }}
    >
      {label}
    </button>
  );
}

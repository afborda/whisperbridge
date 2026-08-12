import { ConnectionStatus } from "../hooks/useTranslationSocket";

interface Props {
  connStatus: ConnectionStatus;
  isRunning: boolean;
  device: string;
  onStart: () => void;
  onPause: () => void;
  onClear: () => void;
}

const STATUS_COLOR: Record<ConnectionStatus, string> = {
  connected:    "#22c55e",
  connecting:   "#f59e0b",
  disconnected: "#ef4444",
  error:        "#ef4444",
};

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connected:    "conectado",
  connecting:   "conectando...",
  disconnected: "desconectado",
  error:        "erro",
};

export function ControlBar({ connStatus, isRunning, device, onStart, onPause, onClear }: Props) {
  const connected = connStatus === "connected";

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "4px 10px",
        background: "rgba(0,0,0,0.75)",
        borderRadius: 6,
        margin: "0 10px 6px",
        userSelect: "none",
      }}
      data-tauri-drag-region
    >
      {/* dot de status */}
      <div style={{
        width: 8, height: 8,
        borderRadius: "50%",
        background: STATUS_COLOR[connStatus],
        flexShrink: 0,
      }} />

      <span style={{
        color: "rgba(255,255,255,0.60)",
        fontSize: 11,
        fontFamily: "Segoe UI, sans-serif",
        flexGrow: 1,
        overflow: "hidden",
        textOverflow: "ellipsis",
        whiteSpace: "nowrap",
      }}>
        {connected && device
          ? device.replace(" [Loopback]", "")
          : STATUS_LABEL[connStatus]}
      </span>

      {/* botões */}
      {connected && !isRunning && (
        <Btn onClick={onStart} color="#2563eb" label="▶ Iniciar" />
      )}
      {connected && isRunning && (
        <Btn onClick={onPause} color="#d97706" label="⏸ Pausar" />
      )}
      <Btn onClick={onClear} color="#374151" label="✕" />
    </div>
  );
}

function Btn({ onClick, color, label }: { onClick: () => void; color: string; label: string }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: color,
        color: "#fff",
        border: "none",
        borderRadius: 4,
        padding: "3px 9px",
        fontSize: 11,
        fontFamily: "Segoe UI, sans-serif",
        cursor: "pointer",
        flexShrink: 0,
        lineHeight: 1.5,
      }}
    >
      {label}
    </button>
  );
}

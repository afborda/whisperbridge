import { useEffect, useRef, useState } from "react";
import { AudioDevice, AudioSource, AudioState } from "../hooks/useTranslationSocket";

interface Props {
  state: AudioState;
  onSelect: (source: AudioSource, index: number | null) => void;
}

const NOME: Record<AudioSource, string> = {
  loopback: "Som do computador",
  mic: "Microfone",
};

export function AudioSourcePicker({ state, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (!open) return;
    const place = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      const width = 320;
      const left = Math.max(8, Math.min(r.right - width, window.innerWidth - width - 8));
      setPos({ top: r.bottom + 6, left });
    };
    place();
    const fora = (e: MouseEvent) => {
      const t = e.target as Node;
      if (menuRef.current?.contains(t) || btnRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", fora);
    window.addEventListener("resize", place);
    return () => {
      document.removeEventListener("mousedown", fora);
      window.removeEventListener("resize", place);
    };
  }, [open]);

  const devices = (s: AudioSource) => state.devices.filter(d => d.source === s);
  const currentName =
    state.devices.find(d => d.source === state.source && d.index === state.deviceIndex)?.name
    ?? (state.source === "mic" ? "microfone padrão" : "saída padrão do Windows");

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 0 }} data-tauri-drag-region={false}>
      <span style={{ color: "rgba(255,255,255,0.35)", fontSize: 10, flexShrink: 0 }}>Ouvir</span>

      <Toggle
        ativo={state.source === "loopback"}
        label="Som do PC"
        title="O que o computador está tocando (Teams, YouTube, reunião)"
        onClick={() => onSelect("loopback", null)}
      />
      <Toggle
        ativo={state.source === "mic"}
        label="Microfone"
        title="A sua voz / microfone do computador"
        onClick={() => onSelect("mic", null)}
      />

      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen(o => !o)}
        title="Escolher o aparelho"
        style={{
          minWidth: 0,
          maxWidth: 180,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
          background: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 6,
          color: "#cbd5e1",
          padding: "3px 8px",
          font: "400 11px system-ui, sans-serif",
          cursor: "pointer",
        }}
      >
        {currentName} ▾
      </button>

      {open && (
        <div
          ref={menuRef}
          style={{
            position: "fixed",
            top: pos.top,
            left: pos.left,
            width: 320,
            zIndex: 90,
            maxHeight: "min(360px, calc(100vh - 80px))",
            overflowY: "auto",
            background: "rgba(15,17,28,0.99)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 8,
            boxShadow: "0 12px 32px rgba(0,0,0,0.6)",
            padding: 4,
          }}
        >
          {(["loopback", "mic"] as AudioSource[]).map(fonte => (
            <div key={fonte}>
              <div style={{
                padding: "8px 8px 3px", color: "rgba(255,255,255,0.40)",
                fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em",
              }}>
                {NOME[fonte]} — {fonte === "loopback" ? "o que o PC toca" : "sua voz"}
              </div>
              <Item
                ativo={state.source === fonte && state.deviceIndex === null}
                titulo="Automático"
                sub={fonte === "mic" ? "microfone padrão do Windows" : "saída padrão do Windows"}
                onClick={() => { onSelect(fonte, null); setOpen(false); }}
              />
              {devices(fonte).map((d: AudioDevice) => (
                <Item
                  key={d.index}
                  ativo={state.source === fonte && state.deviceIndex === d.index}
                  titulo={d.name}
                  sub={d.isDefault ? "padrão do sistema" : `aparelho #${d.index}`}
                  onClick={() => { onSelect(fonte, d.index); setOpen(false); }}
                />
              ))}
              {devices(fonte).length === 0 && (
                <div style={{ padding: "4px 8px 8px", color: "rgba(255,255,255,0.30)", fontSize: 11 }}>
                  Nenhum aparelho listado nesta categoria.
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Toggle({
  ativo, label, title, onClick,
}: { ativo: boolean; label: string; title: string; onClick: () => void }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      style={{
        background: ativo ? "rgba(37,99,235,0.85)" : "rgba(255,255,255,0.06)",
        border: ativo ? "1px solid rgba(147,197,253,0.5)" : "1px solid rgba(255,255,255,0.10)",
        borderRadius: 6,
        color: "#fff",
        padding: "3px 10px",
        font: "600 11px system-ui, sans-serif",
        cursor: "pointer",
        flexShrink: 0,
      }}
    >
      {label}
    </button>
  );
}

function Item({ ativo, titulo, sub, onClick }: {
  ativo: boolean; titulo: string; sub?: string; onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "block", width: "100%", textAlign: "left",
        background: ativo ? "rgba(37,99,235,0.22)" : "transparent",
        border: "none", borderRadius: 5, padding: "6px 8px",
        color: ativo ? "#fff" : "rgba(255,255,255,0.78)",
        font: "500 12px system-ui, sans-serif", cursor: "pointer",
      }}
    >
      {titulo}
      {sub && (
        <span style={{ display: "block", color: "rgba(255,255,255,0.35)", fontSize: 10 }}>
          {sub}
        </span>
      )}
    </button>
  );
}

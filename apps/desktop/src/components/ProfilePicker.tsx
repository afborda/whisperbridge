import { useEffect, useRef, useState } from "react";
import type { Profile, ProfileState } from "../hooks/useTranslationSocket";

interface Props {
  state: ProfileState;
  switching: boolean;
  error: string | null;
  onSelect: (id: string) => void;
  onOpenIaSetup?: () => void;
}

/**
 * Seletor de perfil. O número que importa aqui é a VRAM: o motivo de existir o
 * perfil leve é liberar a placa para outra coisa, então o usuário precisa ver
 * quanto está ocupado agora, não só qual modo está ativo.
 */
export function ProfilePicker({ state, switching, error, onSelect, onOpenIaSetup }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  const active = state.profile;
  const vram = state.vramGb ?? 0;

  return (
    <div ref={ref} style={{ position: "relative" }} data-tauri-drag-region={false}>
      <button
        onClick={() => setOpen(o => !o)}
        disabled={switching}
        title={active?.description ?? "Perfil de execução"}
        style={{
          display: "flex", alignItems: "center", gap: 6,
          background: "rgba(255,255,255,0.06)",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 6, padding: "3px 8px",
          color: switching ? "#94a3b8" : "#e2e8f0",
          font: "500 11px system-ui, sans-serif",
          cursor: switching ? "wait" : "pointer",
        }}
      >
        <span
          style={{
            width: 6, height: 6, borderRadius: "50%",
            background: switching ? "#fbbf24" : vram > 0 ? "#4ade80" : "#60a5fa",
            flexShrink: 0,
          }}
        />
        {switching ? "trocando…" : active?.label ?? "Modo"}
        {state.cloud && (
          <span style={{ fontSize: 10, color: "#93c5fd" }} title="Tradução por IA">IA</span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 50,
            width: 300, padding: 4,
            background: "rgba(15,17,28,0.98)",
            border: "1px solid rgba(255,255,255,0.10)",
            borderRadius: 8,
            boxShadow: "0 12px 32px rgba(0,0,0,0.6)",
          }}
        >
          {state.profiles.map((p: Profile) => {
            const isActive = p.id === active?.id;
            const wantsIa = p.needs_key || p.setupNeeded;
            return (
              <button
                key={p.id}
                disabled={!p.available || switching}
                onClick={() => {
                  setOpen(false);
                  if (wantsIa) onOpenIaSetup?.();
                  if (!isActive) onSelect(p.id);
                }}
                title={p.available ? p.description : p.unavailable_reason}
                style={{
                  display: "block", width: "100%", textAlign: "left",
                  padding: "7px 9px", marginBottom: 2,
                  background: isActive ? "rgba(96,165,250,0.14)" : "transparent",
                  border: "none", borderRadius: 6,
                  cursor: p.available && !switching ? "pointer" : "not-allowed",
                  opacity: p.available ? 1 : 0.42,
                  color: "#e2e8f0",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ font: "600 12px system-ui, sans-serif" }}>{p.label}</span>
                </div>
                <div style={{ font: "400 10.5px system-ui, sans-serif", color: "#94a3b8", marginTop: 2, lineHeight: 1.35 }}>
                  {!p.available
                    ? p.unavailable_reason
                    : p.setupNeeded
                      ? "Abre idiomas + campo da chave da IA."
                      : p.description}
                </div>
              </button>
            );
          })}

          <div style={{ padding: "6px 9px 3px", borderTop: "1px solid rgba(255,255,255,0.07)", marginTop: 3 }}>
            <div style={{ font: "400 10px system-ui, sans-serif", color: "#64748b", lineHeight: 1.4 }}>
              {vram > 0 ? `Placa em uso: ${vram} GB. ` : "Placa livre. "}
              Ir para a IA é instantâneo se o ouvido já estiver carregado.
            </div>
          </div>
        </div>
      )}

      {error && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 60,
            width: 260, padding: "7px 9px",
            background: "rgba(127,29,29,0.96)",
            border: "1px solid rgba(248,113,113,0.4)",
            borderRadius: 6,
            font: "500 11px system-ui, sans-serif", color: "#fecaca",
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}

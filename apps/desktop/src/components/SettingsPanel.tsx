import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import type { LangOption, UserSettings } from "../hooks/useTranslationSocket";

interface Props {
  open: boolean;
  settings: UserSettings | null;
  cloud: boolean;
  saving: boolean;
  onClose: () => void;
  onSave: (payload: Record<string, string>) => void;
}

export function SettingsPanel({ open, settings, cloud, saving, onClose, onSave }: Props) {
  const [sourceLang, setSourceLang] = useState("en");
  const [targetLang, setTargetLang] = useState("pt-BR");
  const [backend, setBackend] = useState("gemini");
  const [apiKey, setApiKey] = useState("");
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [showKey, setShowKey] = useState(false);

  // Só preenche ao ABRIR. Se atualizar no meio, não reseta o que a pessoa está digitando.
  useEffect(() => {
    if (!open || !settings) return;
    setSourceLang(settings.sourceLang);
    setTargetLang(settings.targetLang);
    setBackend(settings.backend);
    setApiKey("");
    setLlmBaseUrl(settings.llmBaseUrl);
    setLlmModel(settings.llmModel);
    setShowKey(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open || !settings) return null;

  const langs = settings.languages ?? [];
  const hasKey = backend === "gemini" ? settings.hasGeminiKey : settings.hasLlmKey;

  function save() {
    const payload: Record<string, string> = {
      sourceLang,
      targetLang,
      backend,
    };
    if (apiKey.trim()) payload.apiKey = apiKey.trim();
    if (backend === "openai-compat") {
      payload.llmBaseUrl = llmBaseUrl;
      payload.llmModel = llmModel;
    }
    if (backend === "claude" && llmModel.trim()) {
      payload.llmModel = llmModel.trim();
    }
    onSave(payload);
  }

  return (
    <div
      onMouseDown={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 80,
        background: "rgba(0,0,0,0.45)",
        display: "flex", alignItems: "flex-start", justifyContent: "center",
        padding: "40px 12px 12px",
      }}
    >
      <div
        onMouseDown={e => e.stopPropagation()}
        style={{
          width: 400, maxWidth: "100%",
          maxHeight: "calc(100vh - 56px)",
          overflow: "auto",
          background: "rgba(15,17,28,0.98)",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 10,
          boxShadow: "0 16px 40px rgba(0,0,0,0.65)",
          color: "#e2e8f0",
          font: "400 12px system-ui, sans-serif",
        }}
      >
        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "10px 14px 8px",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
        }}>
          <strong style={{ fontSize: 13 }}>Idiomas e chave da IA</strong>
          <button onClick={onClose} style={iconBtn} type="button">✕</button>
        </div>

        <div style={{ padding: "12px 14px 6px" }}>
          <Label>Idioma que estão falando</Label>
          <LangPicker
            value={sourceLang}
            options={langs}
            onChange={setSourceLang}
          />

          <Label>Idioma da legenda</Label>
          <LangPicker
            value={targetLang.startsWith("pt") ? "pt" : targetLang}
            options={langs.filter(l => l.id !== "auto")}
            onChange={v => setTargetLang(v === "pt" ? "pt-BR" : v)}
          />

          {!cloud && (
            <p style={hint}>
              Sem IA a tradução local é só inglês → português.
              Com <b>Recomendado (IA)</b> você escolhe qualquer par
              (espanhol→português, inglês→tailandês, português→japonês…).
            </p>
          )}
          {cloud && (
            <p style={hint}>
              A IA traduz o par que você escolher acima. Claude, Gemini, GPT —
              o áudio continua neste PC; só o texto vai para a API.
            </p>
          )}
        </div>

        <div style={{ padding: "8px 14px 14px", borderTop: "1px solid rgba(255,255,255,0.07)" }}>
          <Label>Sua IA para traduzir</Label>
          <div style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
            <Chip on={backend === "gemini"} onClick={() => setBackend("gemini")}>Gemini</Chip>
            <Chip on={backend === "claude"} onClick={() => {
              setBackend("claude");
              if (!llmModel || /gpt|deepseek|moonshot|minimax/i.test(llmModel)) {
                setLlmModel("claude-3-5-haiku-latest");
              }
            }}>Claude</Chip>
            <Chip on={backend === "openai-compat"} onClick={() => setBackend("openai-compat")}>
              GPT / outra
            </Chip>
          </div>

          <Label>
            Chave da API {hasKey && !apiKey && <span style={{ color: "#4ade80" }}> · já salva</span>}
          </Label>
          <div style={{ display: "flex", gap: 6 }}>
            <input
              type={showKey ? "text" : "password"}
              value={apiKey}
              placeholder={hasKey ? "••••••••  (cole outra para trocar)" : "Cole a chave aqui"}
              onChange={e => setApiKey(e.target.value)}
              style={input}
            />
            <button type="button" onClick={() => setShowKey(s => !s)} style={iconBtn}>
              {showKey ? "ocultar" : "ver"}
            </button>
          </div>

          {backend === "claude" && (
            <>
              <Label>Modelo</Label>
              <input
                value={llmModel || "claude-3-5-haiku-latest"}
                onChange={e => setLlmModel(e.target.value)}
                placeholder="claude-3-5-haiku-latest"
                style={input}
              />
            </>
          )}

          {backend === "openai-compat" && (
            <>
              <Label>Endereço da API</Label>
              <input value={llmBaseUrl} onChange={e => setLlmBaseUrl(e.target.value)} style={input} />
              <Label>Modelo</Label>
              <input value={llmModel} onChange={e => setLlmModel(e.target.value)} style={input} />
            </>
          )}

          <p style={hint}>
            A chave fica só neste computador. Mudar o idioma da legenda é instantâneo.
            Mudar o idioma que estão falando baixa o Whisper multilíngue na primeira vez.
          </p>

          <button
            type="button"
            onClick={save}
            disabled={saving}
            style={{
              ...input,
              marginTop: 10,
              background: "#2563eb",
              border: "none",
              fontWeight: 600,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Salvando…" : "Salvar"}
          </button>
        </div>
      </div>
    </div>
  );
}

function LangPicker({
  value, options, onChange,
}: {
  value: string;
  options: LangOption[];
  onChange: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find(o => o.id === value) ?? options[0];

  return (
    <div style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        style={{ ...input, textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
      >
        <span>{current?.label ?? value}</span>
        <span style={{ color: "#64748b" }}>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div
          style={{
            position: "absolute", left: 0, right: 0, top: "calc(100% + 4px)",
            zIndex: 90,
            maxHeight: 220,
            overflowY: "auto",
            background: "rgba(15,17,28,0.99)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 6,
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
          }}
        >
          {options.map(o => (
            <button
              key={o.id}
              type="button"
              onClick={() => { onChange(o.id); setOpen(false); }}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "7px 10px",
                border: "none",
                background: o.id === value ? "rgba(96,165,250,0.16)" : "transparent",
                color: "#e2e8f0",
                font: "400 12px system-ui, sans-serif",
                cursor: "pointer",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Label({ children }: { children: ReactNode }) {
  return (
    <div style={{ color: "#94a3b8", fontSize: 10.5, margin: "8px 0 4px", letterSpacing: "0.03em" }}>
      {children}
    </div>
  );
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        flex: 1,
        padding: "6px 8px",
        borderRadius: 6,
        border: on ? "1px solid rgba(96,165,250,0.6)" : "1px solid rgba(255,255,255,0.10)",
        background: on ? "rgba(96,165,250,0.16)" : "rgba(255,255,255,0.04)",
        color: "#e2e8f0",
        font: "600 11px system-ui, sans-serif",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

const input: CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: "rgba(255,255,255,0.06)",
  border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 6,
  color: "#e2e8f0",
  padding: "6px 8px",
  font: "400 12px system-ui, sans-serif",
};

const iconBtn: CSSProperties = {
  background: "transparent",
  border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 6,
  color: "#94a3b8",
  cursor: "pointer",
  padding: "4px 8px",
  font: "500 11px system-ui, sans-serif",
  flexShrink: 0,
};

const hint: CSSProperties = {
  color: "#64748b",
  fontSize: 10.5,
  lineHeight: 1.4,
  margin: "8px 0 0",
};

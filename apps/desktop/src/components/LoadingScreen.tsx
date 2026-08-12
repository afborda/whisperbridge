import { useEffect, useState } from "react";

type Phase =
  | "ui"
  | "waiting-engine"
  | "loading-models"
  | "connecting"
  | "ready"
  | "error";

const PHASE_LABEL: Record<Phase, string> = {
  ui: "Interface pronta",
  "waiting-engine": "Aguardando motor de IA…",
  "loading-models": "Carregando Whisper e tradutor…",
  connecting: "Conectando ao engine…",
  ready: "Tudo pronto",
  error: "Não foi possível iniciar",
};

const STEPS: Phase[] = [
  "ui",
  "waiting-engine",
  "loading-models",
  "connecting",
  "ready",
];

interface Props {
  phase: Phase;
  detail?: string;
  onRetry?: () => void;
}

export function LoadingScreen({ phase, detail, onRetry }: Props) {
  const [pulse, setPulse] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setPulse((p) => p + 1), 80);
    return () => clearInterval(t);
  }, []);

  const activeIdx = Math.max(0, STEPS.indexOf(phase === "error" ? "waiting-engine" : phase));

  return (
    <div className="wb-boot">
      <div className="wb-boot-glow" />
      <div className="wb-boot-grid" />

      <div className="wb-boot-center">
        {/* Orbe multi-cor */}
        <div className="wb-orb" aria-hidden>
          <div className="wb-orb-ring r1" />
          <div className="wb-orb-ring r2" />
          <div className="wb-orb-ring r3" />
          <div className="wb-orb-core">
            <span className="wb-orb-core-shine" style={{ opacity: 0.55 + (pulse % 10) * 0.04 }} />
          </div>
          <div className="wb-orb-spark s1" />
          <div className="wb-orb-spark s2" />
          <div className="wb-orb-spark s3" />
          <div className="wb-orb-spark s4" />
        </div>

        <h1 className="wb-boot-title">
          Whisper<span>Bridge</span>
        </h1>
        <p className="wb-boot-sub">Legendas em tempo real · IA local</p>

        <div className="wb-boot-status">
          <span className={`wb-boot-dot ${phase === "error" ? "err" : "ok"}`} />
          <span>{PHASE_LABEL[phase]}</span>
        </div>
        {detail && <p className="wb-boot-detail">{detail}</p>}

        {/* Steps */}
        <ul className="wb-boot-steps">
          {STEPS.map((s, i) => {
            const done = phase === "ready" || i < activeIdx;
            const current = phase !== "error" && i === activeIdx && phase !== "ready";
            return (
              <li key={s} className={done ? "done" : current ? "current" : ""}>
                <span className="wb-step-mark">{done ? "✓" : current ? "●" : "○"}</span>
                {PHASE_LABEL[s]}
              </li>
            );
          })}
        </ul>

        {phase === "error" && (
          <button type="button" className="wb-boot-retry" onClick={onRetry}>
            Tentar de novo
          </button>
        )}

        {phase !== "error" && phase !== "ready" && (
          <div className="wb-boot-bar">
            <div className="wb-boot-bar-fill" />
          </div>
        )}
      </div>
    </div>
  );
}

export type { Phase };

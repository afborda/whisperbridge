import { useCallback, useEffect, useState } from "react";
import type { Phase } from "../components/LoadingScreen";
import { ENGINE_HEALTH } from "../config";

/**
 * A UI nunca desiste. Se o Python cair, volta para a tela de espera e
 * reconecta sozinha quando o engine subir de novo.
 */
export function useEngineReady() {
  const [phase, setPhase] = useState<Phase>("waiting-engine");
  const [detail, setDetail] = useState("Aguardando o servidor local…");
  const [ready, setReady] = useState(false);

  const retry = useCallback(() => {
    setReady(false);
    setPhase("waiting-engine");
    setDetail("Tentando novamente…");
  }, []);

  useEffect(() => {
    let cancelled = false;
    let waitingSince = Date.now();

    const tick = async () => {
      if (cancelled) return;
      const waited = Math.round((Date.now() - waitingSince) / 1000);

      try {
        const ctrl = new AbortController();
        const t = window.setTimeout(() => ctrl.abort(), 2000);
        const res = await fetch(ENGINE_HEALTH, { signal: ctrl.signal });
        window.clearTimeout(t);
        if (!res.ok) throw new Error(String(res.status));
        const data = (await res.json()) as { status?: string; error?: string };

        if (cancelled) return;

        if (data.status === "ok") {
          if (!ready) {
            setPhase("connecting");
            setDetail("Engine online — abrindo legendas…");
            await new Promise(r => setTimeout(r, 300));
          }
          if (!cancelled) {
            setPhase("ready");
            setDetail("");
            setReady(true);
          }
        } else if (data.status === "loading") {
          setReady(false);
          setPhase("loading-models");
          setDetail("Servidor no ar — carregando os modelos…");
        } else if (data.status === "error") {
          setReady(false);
          setPhase("error");
          setDetail(data.error || "Falha ao carregar os modelos. O app continua tentando…");
        }
      } catch {
        if (cancelled) return;
        if (ready) waitingSince = Date.now();
        setReady(false);
        setPhase("waiting-engine");
        setDetail(
          waited < 5
            ? "Aguardando o servidor local…"
            : `Servidor desligado. Reconectando… ${waited}s`,
        );
      }

      if (!cancelled) {
        window.setTimeout(tick, 900);
      }
    };

    tick();
    return () => {
      cancelled = true;
    };
  }, [ready]);

  return { ready, phase, detail, retry };
}

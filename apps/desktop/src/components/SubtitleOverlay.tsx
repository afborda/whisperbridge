import { useEffect, useRef, Fragment } from "react";
import { SubtitleSegment } from "../hooks/useTranslationSocket";

interface Props {
  history: SubtitleSegment[];
  livePartial: SubtitleSegment | null;
}

function formatTime(ts: number) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function SubtitleOverlay({ history, livePartial }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // auto-scroll para o final sempre que chegar conteúdo novo
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [history.length, livePartial?.sourceText]);

  const isEmpty = history.length === 0 && !livePartial;

  return (
    <div style={{
      flex: 1,
      overflowY: "auto",
      overflowX: "hidden",
      padding: "10px 0 6px",
      scrollbarWidth: "thin",
      scrollbarColor: "rgba(255,255,255,0.12) transparent",
    }}>
      {isEmpty && (
        <div style={{
          padding: "20px 18px",
          color: "rgba(255,255,255,0.25)",
          fontSize: 15,
          fontStyle: "italic",
          textAlign: "center",
          letterSpacing: "0.02em",
        }}>
          Aguardando fala…
        </div>
      )}

      {history.map((seg, idx) => {
        const prev = history[idx - 1];
        const gap  = prev ? seg.startedAt - prev.startedAt : 0;
        const newSpeaker = prev && gap > 2.5;

        return (
          <Fragment key={seg.id}>
            {newSpeaker && (
              <div style={{
                height: 1,
                background: "rgba(255,255,255,0.07)",
                margin: "10px 14px",
              }} />
            )}

            <div style={{
              display: "flex",
              gap: 10,
              padding: "6px 14px",
              animation: "fadeSlideIn 0.25s ease",
            }}>
              {/* barra colorida lateral — indica falante */}
              <div style={{
                width: 3,
                borderRadius: 2,
                background: seg.speakerColor,
                flexShrink: 0,
                opacity: 0.8,
                alignSelf: "stretch",
                minHeight: 20,
              }} />

              <div style={{ flex: 1, minWidth: 0 }}>
                {/* hora + falante */}
                <div style={{
                  display: "flex",
                  gap: 6,
                  alignItems: "center",
                  marginBottom: 3,
                }}>
                  <span style={{
                    fontSize: 10,
                    color: "rgba(255,255,255,0.28)",
                    letterSpacing: "0.06em",
                    fontVariantNumeric: "tabular-nums",
                  }}>
                    {formatTime(seg.startedAt)}
                  </span>
                  {seg.speakerId && (
                    <span style={{
                      fontSize: 10,
                      fontWeight: 600,
                      color: seg.speakerColor,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      opacity: 0.9,
                    }}>
                      {seg.speakerId}
                    </span>
                  )}
                </div>

                {/* texto traduzido.
                    Enquanto a revisão da nuvem não chega a linha fica levemente
                    apagada — assim a troca de texto ~700ms depois não parece um
                    glitch, o usuário já sabia que aquilo era provisório. */}
                <div style={{
                  color: seg.willRevise ? "rgba(241,245,249,0.72)" : "#f1f5f9",
                  fontSize: 20,
                  fontWeight: 500,
                  lineHeight: 1.45,
                  letterSpacing: "0.01em",
                  wordBreak: "break-word",
                  transition: "color 0.3s ease",
                }}>
                  {seg.translatedText || seg.sourceText}
                </div>
              </div>
            </div>
          </Fragment>
        );
      })}

      {/* partial ao vivo — texto em inglês aparecendo enquanto alguém fala */}
      {livePartial && (
        <div style={{
          display: "flex",
          gap: 10,
          padding: "6px 14px",
          animation: "fadeSlideIn 0.15s ease",
        }}>
          <div style={{
            width: 3,
            borderRadius: 2,
            background: livePartial.speakerColor,
            flexShrink: 0,
            opacity: 0.5,
            alignSelf: "stretch",
            minHeight: 20,
          }} />

          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 10,
              color: "rgba(255,255,255,0.2)",
              marginBottom: 3,
              letterSpacing: "0.06em",
            }}>
              ao vivo
            </div>
            <div style={{
              color: "rgba(255,255,255,0.70)",
              fontSize: 20,
              fontWeight: 400,
              lineHeight: 1.45,
              fontStyle: "italic",
              wordBreak: "break-word",
            }}>
              {livePartial.sourceText}
              <span style={{
                display: "inline-block",
                width: 2,
                height: "1em",
                background: "rgba(255,255,255,0.6)",
                marginLeft: 3,
                verticalAlign: "text-bottom",
                animation: "blink 1s ease infinite",
              }} />
            </div>
          </div>
        </div>
      )}

      {/* âncora de scroll */}
      <div ref={bottomRef} style={{ height: 4 }} />
    </div>
  );
}

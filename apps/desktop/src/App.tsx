import "./App.css";
import { useTranslationSocket } from "./hooks/useTranslationSocket";
import { useEngineReady } from "./hooks/useEngineReady";
import { SubtitleOverlay } from "./components/SubtitleOverlay";
import { TitleBar } from "./components/TitleBar";
import { LoadingScreen } from "./components/LoadingScreen";
import { AudioSourcePicker } from "./components/AudioSourcePicker";

export default function App() {
  const { ready, phase, detail, retry } = useEngineReady();
  const {
    connStatus, isRunning, history, livePartial, device, start, pause, clear,
    profileState, switching, profileError, setProfile, cost,
    audio, setAudioSource, settings, saveSettings,
  } = useTranslationSocket();

  // Enquanto o engine não sobe, só a tela de boot (nunca página de erro do browser)
  if (!ready) {
    return <LoadingScreen phase={phase} detail={detail} onRetry={retry} />;
  }

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "transparent",
        padding: 0,
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "rgba(9, 10, 19, 0.92)",
          backdropFilter: "blur(16px)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 10,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 12px 40px rgba(0,0,0,0.70)",
        }}
      >
        <TitleBar
          connStatus={connStatus}
          isRunning={isRunning}
          device={device}
          segCount={history.length}
          onStart={start}
          onPause={pause}
          onClear={clear}
          profileState={profileState}
          switching={switching}
          profileError={profileError}
          onSetProfile={setProfile}
          cost={cost}
          settings={settings}
          onSaveSettings={saveSettings}
        />

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            padding: "6px 10px",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
            flexShrink: 0,
            background: "rgba(255,255,255,0.02)",
          }}
        >
          <AudioSourcePicker state={audio} onSelect={setAudioSource} />
        </div>

        <SubtitleOverlay history={history} livePartial={livePartial} />

        <div
          style={{
            height: 4,
            background: "transparent",
            cursor: "ns-resize",
            flexShrink: 0,
          }}
        />
      </div>
    </div>
  );
}

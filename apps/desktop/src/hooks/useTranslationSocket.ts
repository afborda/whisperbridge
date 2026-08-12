import { useEffect, useRef, useState, useCallback } from "react";
import { ENGINE_WS } from "../config";

export interface SubtitleSegment {
  id: string;
  sourceText: string;
  translatedText?: string;
  status: "partial" | "translated";
  startedAt: number;
  speakerColor: string;
  speakerId: string | null;   // "Pessoa 1", "Pessoa 2", etc. — null se pyannote não disponível
  willRevise?: boolean;       // uma versão da nuvem ainda vai chegar
  revised?: boolean;          // já foi substituída pela versão da nuvem
}

export type ConnectionStatus = "disconnected" | "connecting" | "connected" | "error";

export interface Profile {
  id: string;
  label: string;
  description: string;
  whisper_device: string;
  whisper_model: string;
  translator: string;
  approx_vram_gb: number;
  available: boolean;
  unavailable_reason: string;
  needs_key?: boolean;
  setupNeeded?: boolean;
}

export interface ProfileState {
  profile: Profile | null;
  profiles: Profile[];
  vramGb: number;
  cloud: boolean;
}

export interface LangOption {
  id: string;
  label: string;
}

export interface UserSettings {
  sourceLang: string;
  targetLang: string;
  backend: string;
  geminiModel: string;
  llmBaseUrl: string;
  llmModel: string;
  hasGeminiKey: boolean;
  hasLlmKey: boolean;
  languages: LangOption[];
}

/** Consumo acumulado da nuvem nesta sessão. Zera quando o engine reinicia. */
export interface CostState {
  calls: number;
  tokensIn: number;
  tokensOut: number;
  usd: number;
  model: string | null;
  /** false = modelo sem preço conhecido no servidor; mostrar tokens, não dinheiro */
  priced: boolean;
}

const NO_COST: CostState = {
  calls: 0, tokensIn: 0, tokensOut: 0, usd: 0, model: null, priced: true,
};

export type AudioSource = "loopback" | "mic";

export interface AudioDevice {
  index: number;
  name: string;
  source: AudioSource;
  isDefault: boolean;
}

export interface AudioState {
  source: AudioSource;
  deviceIndex: number | null;   // null = automático dentro da fonte
  devices: AudioDevice[];
}

const NO_AUDIO: AudioState = { source: "loopback", deviceIndex: null, devices: [] };

// Paleta de cores por falante (heurística: pausa > 2.5s = novo falante)
const SPEAKER_COLORS = [
  "#60a5fa",  // azul
  "#4ade80",  // verde
  "#c4b5fd",  // lilás
  "#fbbf24",  // âmbar
  "#f472b6",  // rosa
  "#34d399",  // esmeralda
  "#fb923c",  // laranja
  "#a5f3fc",  // ciano
];

export function useTranslationSocket(url = ENGINE_WS) {
  const ws            = useRef<WebSocket | null>(null);
  const reconnTimer   = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const colorIdxRef   = useRef(0);
  const lastEndedAt   = useRef(0);

  const [connStatus, setConnStatus]   = useState<ConnectionStatus>("disconnected");
  const [isRunning, setIsRunning]     = useState(false);
  const [history, setHistory]         = useState<SubtitleSegment[]>([]);
  const [livePartial, setLivePartial] = useState<SubtitleSegment | null>(null);
  const [device, setDevice]           = useState("");
  const [profileState, setProfileState] = useState<ProfileState>({
    profile: null, profiles: [], vramGb: 0, cloud: false,
  });
  const [switching, setSwitching]     = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [cost, setCost]               = useState<CostState>(NO_COST);
  const [audio, setAudio]             = useState<AudioState>(NO_AUDIO);
  const [settings, setSettings]       = useState<UserSettings | null>(null);

  const send = useCallback((msg: object) => {
    if (ws.current?.readyState === WebSocket.OPEN)
      ws.current.send(JSON.stringify(msg));
  }, []);

  const connect = useCallback(() => {
    if (ws.current?.readyState === WebSocket.OPEN) return;
    setConnStatus("connecting");
    const socket = new WebSocket(url);
    ws.current = socket;

    socket.onopen  = () => setConnStatus("connected");
    socket.onerror = () => setConnStatus("error");
    socket.onclose = () => {
      setConnStatus("disconnected");
      setIsRunning(false);
      reconnTimer.current = setTimeout(connect, 3000);
    };

    socket.onmessage = ({ data }) => {
      const msg = JSON.parse(data);

      if (msg.type === "status") {
        setIsRunning(msg.data.state === "running");
        if (msg.data.device) setDevice(msg.data.device);
        if (msg.data.state === "loading") setSwitching(true);
      }

      if (msg.type === "profiles") {
        setProfileState(msg.data);
        if (msg.data.cost) setCost(msg.data.cost);
        if (msg.data.audio) setAudio(msg.data.audio);
        if (msg.data.settings) setSettings(msg.data.settings);
      }

      if (msg.type === "settings") {
        setSettings(msg.data);
        setSwitching(false);
      }

      if (msg.type === "audio") {
        setAudio(msg.data);
        return;
      }

      // Chega junto com cada revisão da nuvem — é o único momento em que
      // o gasto muda, então não precisa de polling.
      if (msg.type === "cost") {
        setCost(msg.data);
        return;
      }

      if (msg.type === "profile_changed") {
        setSwitching(false);
        setProfileError(msg.data.error ?? null);
        setProfileState(prev => ({
          ...prev,
          profile: msg.data.profile,
          vramGb: msg.data.vramGb,
          cloud: msg.data.cloud,
        }));
      }

      if (msg.type === "profile_error") {
        setSwitching(false);
        setProfileError(msg.data.error);
      }

      // Revisão da nuvem: substitui o texto da linha que já está na tela.
      // Chega ~700ms depois da legenda local, com o mesmo id.
      if (msg.type === "subtitle_revision") {
        const { id, translatedText } = msg.data;
        setHistory(prev => prev.map(seg =>
          seg.id === id
            ? { ...seg, translatedText, revised: true, willRevise: false }
            : seg
        ));
        return;
      }

      if (msg.type === "subtitle") {
        const seg = msg.data;

        if (seg.status === "partial") {
          setLivePartial({
            ...seg,
            speakerColor: SPEAKER_COLORS[colorIdxRef.current % SPEAKER_COLORS.length],
          });
          return;
        }

        // Usar cor real do servidor (pyannote) ou fallback heurístico
        let color: string;
        if (seg.speakerColor) {
          color = seg.speakerColor;
          // sincroniza o índice local com o speaker real
          if (seg.speakerIsNew) colorIdxRef.current += 1;
        } else {
          const gap = seg.startedAt - lastEndedAt.current;
          if (lastEndedAt.current > 0 && gap > 2.5) colorIdxRef.current += 1;
          color = SPEAKER_COLORS[colorIdxRef.current % SPEAKER_COLORS.length];
        }
        lastEndedAt.current = seg.startedAt;

        setLivePartial(null);
        setHistory(prev => [...prev, {
          id:             seg.id,
          sourceText:     seg.sourceText,
          translatedText: seg.translatedText,
          status:         seg.status,
          startedAt:      seg.startedAt,
          speakerColor:   color,
          speakerId:      seg.speakerId ?? null,
          willRevise:     seg.willRevise ?? false,
        }]);
      }
    };
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  useEffect(() => {
    if (!switching) return;
    const t = window.setTimeout(() => setSwitching(false), 25_000);
    return () => window.clearTimeout(t);
  }, [switching]);

  const start = useCallback(() => send({ type: "start" }), [send]);
  const pause = useCallback(() => send({ type: "pause" }), [send]);
  const stop  = useCallback(() => send({ type: "stop" }),  [send]);
  const setProfile = useCallback((profile: string) => {
    setProfileError(null);
    send({ type: "set_profile", profile });
  }, [send]);
  const setAudioSource = useCallback(
    (source: AudioSource, index: number | null = null) =>
      send({ type: "set_audio_source", source, index }),
    [send],
  );
  const saveSettings = useCallback((payload: Record<string, string>) => {
    const family = (s?: string) => (s === "en" || s === "en-us" || !s ? "en" : "multi");
    const srcChanged = payload.sourceLang
      && family(payload.sourceLang) !== family(settings?.sourceLang);
    if (srcChanged) setSwitching(true);
    send({ type: "set_settings", ...payload });
  }, [send, settings]);
  const clear = useCallback(() => {
    setHistory([]);
    setLivePartial(null);
    colorIdxRef.current = 0;
    lastEndedAt.current = 0;
  }, []);

  return {
    connStatus, isRunning, history, livePartial, device,
    start, pause, stop, clear,
    profileState, switching, profileError, setProfile,
    cost, audio, setAudioSource,
    settings, saveSettings,
  };
}

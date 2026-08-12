/**
 * Portas locais do WhisperBridge — manter em sync com shared/ports.py
 * Engine: 37865 (alta, pouco usada por apps padrão)
 * Vite dev: 14287 (só em desenvolvimento)
 */
export const ENGINE_HOST = "127.0.0.1";
export const ENGINE_PORT = 37865;
export const ENGINE_HTTP = `http://${ENGINE_HOST}:${ENGINE_PORT}`;
export const ENGINE_WS = `ws://${ENGINE_HOST}:${ENGINE_PORT}/ws`;
export const ENGINE_HEALTH = `${ENGINE_HTTP}/health`;

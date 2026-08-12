use std::io::Write;
use std::net::TcpStream;
use std::time::Duration;

use tauri::Manager;

/// Avisa o engine Python para descarregar os modelos. Sem isto, fechar pelo
/// X da barra de tarefas (que não passa pelo JS) deixa Whisper na VRAM.
fn request_engine_shutdown() {
    let addr: std::net::SocketAddr = ([127, 0, 0, 1], 37865).into();
    if let Ok(mut stream) =
        TcpStream::connect_timeout(&addr, Duration::from_millis(400))
    {
        let _ = stream.set_write_timeout(Some(Duration::from_millis(400)));
        let _ = stream.set_read_timeout(Some(Duration::from_millis(400)));
        let req = b"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:37865\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        let _ = stream.write_all(req);
        let _ = stream.shutdown(std::net::Shutdown::Both);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // Garante ícone na barra de tarefas / janela (Windows)
            if let Some(window) = app.get_webview_window("main") {
                // skip_taskbar false já está no conf; reforça título
                let _ = window.set_title("WhisperBridge");
                let _ = window.set_skip_taskbar(false);
                window.on_window_event(|event| {
                    if let tauri::WindowEvent::Destroyed = event {
                        request_engine_shutdown();
                    }
                });
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("erro ao iniciar WhisperBridge");
}

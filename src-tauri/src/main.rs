// Hembudget desktop shell.
//
// Responsibilities:
//   1. Spawn the Python FastAPI backend as a sidecar ("hembudget-backend").
//   2. Read the port the backend prints on its first stdout line.
//   3. Inject the port into the webview via localStorage ("hembudget_api_port")
//      so the React app can talk to the backend.
//   4. Shut down the backend cleanly when the window closes.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::api::process::{Command, CommandChild, CommandEvent};
use tauri::Manager;

struct BackendHandle(Mutex<Option<CommandChild>>);

fn main() {
    tauri::Builder::default()
        .manage(BackendHandle(Mutex::new(None)))
        .setup(|app| {
            let handle = app.handle();

            let (mut rx, child) = Command::new_sidecar("hembudget-backend")
                .expect("failed to locate hembudget-backend sidecar")
                .args(["--print-port"])
                .spawn()
                .expect("failed to spawn hembudget-backend");

            {
                let state = app.state::<BackendHandle>();
                *state.0.lock().unwrap() = Some(child);
            }

            tauri::async_runtime::spawn(async move {
                let mut first_line = true;
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            if first_line {
                                first_line = false;
                                if let Ok(port) = line.trim().parse::<u16>() {
                                    if let Some(window) = handle.get_window("main") {
                                        let js = format!(
                                            "window.localStorage.setItem('hembudget_api_port','{port}');"
                                        );
                                        let _ = window.eval(&js);
                                    }
                                }
                            }
                            eprintln!("[backend] {line}");
                        }
                        CommandEvent::Stderr(line) => eprintln!("[backend:err] {line}"),
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event.event() {
                let handle = event.window().app_handle();
                if let Some(state) = handle.try_state::<BackendHandle>() {
                    if let Some(child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Hembudget");
}

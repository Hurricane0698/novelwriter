fn main() {
    let app_manifest =
        tauri_build::AppManifest::new().commands(&["open_logs", "quit", "startup_status"]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(app_manifest))
        .expect("build NovWr desktop application");
}

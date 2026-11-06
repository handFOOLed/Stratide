fn main() {
    let manifest = std::path::PathBuf::from(std::env::var("CARGO_MANIFEST_DIR").expect("manifest"));
    let icon = manifest.join("../../assets/brand/stratide.ico");
    println!("cargo:rerun-if-changed={}", icon.display());
    // cfg(windows) here would be the host. The launcher is cross-checked on
    // Linux, so only the Windows target embeds the resource.
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_os != "windows" {
        return;
    }
    let mut res = winresource::WindowsResource::new();
    res.set_icon(icon.to_str().expect("icon path is utf-8"));
    res.compile()
        .expect("embed assets/brand/stratide.ico into the Windows launcher");
}

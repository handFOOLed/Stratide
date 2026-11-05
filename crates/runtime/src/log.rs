use std::io::Write;
use std::path::{Path, PathBuf};

const MAX_LOG_BYTES: u64 = 8 * 1024 * 1024;

pub fn append(path: &Path, message: &str) {
    let _ = rotate(path);
    let line = format!("{} {message}\n", crate::timestamp());
    if let Some(parent) = path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
    {
        let _ = file.write_all(line.as_bytes());
    }
}

fn rotate(path: &Path) -> std::io::Result<()> {
    let metadata = match std::fs::metadata(path) {
        Ok(metadata) => metadata,
        Err(_) => return Ok(()),
    };
    if metadata.len() < MAX_LOG_BYTES {
        return Ok(());
    }
    let old = PathBuf::from(format!("{}.1", path.display()));
    let _ = std::fs::remove_file(&old);
    std::fs::rename(path, old)
}

pub fn tail(path: &Path, lines: usize) -> Vec<String> {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        Err(_) => return Vec::new(),
    };
    let start = bytes.len().saturating_sub(64 * 1024);
    let text = String::from_utf8_lossy(&bytes[start..]);
    let mut rows: Vec<String> = text.lines().map(|line| line.to_string()).collect();
    if rows.len() > lines {
        rows = rows.split_off(rows.len() - lines);
    }
    rows
}

use std::{
    fs::{self, OpenOptions},
    io::{ErrorKind, Write},
    path::Path,
};

#[derive(PartialEq, Eq)]
enum Existing {
    Complete,
    Interrupted,
}

/// Recognize only the sequential prefix produced by the original exporter:
/// complete earlier files, at most one truncated file, then absent later files.
/// Even a recognized prefix is archived, never repaired in place.
fn inspect(out: &Path, files: &[(&str, Vec<u8>)]) -> Result<Option<Existing>, String> {
    let metadata = match fs::symlink_metadata(out) {
        Ok(m) => m,
        Err(e) if e.kind() == ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(e.to_string()),
    };
    if !metadata.file_type().is_dir() {
        return Err("报表目标必须为普通目录，不能覆盖文件或链接".into());
    }
    for entry in fs::read_dir(out).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        if !files.iter().any(|(name, _)| entry.file_name() == *name)
            || !entry.file_type().map_err(|e| e.to_string())?.is_file()
        {
            return Err("既有报表包含未知文件/目录/链接；保留原目录，拒绝自动恢复".into());
        }
    }
    let mut interrupted = false;
    for (name, expected) in files {
        match fs::read(out.join(name)) {
            Ok(actual) if !interrupted && actual == *expected => {}
            Ok(actual) if !interrupted && expected.starts_with(&actual) => interrupted = true,
            Ok(_) => {
                return Err(format!(
                    "既有报表 {name} 内容冲突或不符合中断写入顺序；保留原目录"
                ))
            }
            Err(e) if e.kind() == ErrorKind::NotFound => interrupted = true,
            Err(e) => return Err(e.to_string()),
        }
    }
    Ok(Some(if interrupted {
        Existing::Interrupted
    } else {
        Existing::Complete
    }))
}

fn write_file(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|e| e.to_string())?;
    #[cfg(test)]
    {
        let (first, second) = bytes.split_at(bytes.len() / 2);
        file.write_all(first).map_err(|e| e.to_string())?;
        file.sync_all().map_err(|e| e.to_string())?;
        fault("partial_file");
        file.write_all(second).map_err(|e| e.to_string())?;
    }
    #[cfg(not(test))]
    file.write_all(bytes).map_err(|e| e.to_string())?;
    file.sync_all().map_err(|e| e.to_string())
}

/// Publish all six derived reports as one same-filesystem directory rename.
/// The authoritative ledger is never written by this module. Temporary remnants
/// after process death and archived legacy prefixes remain separate evidence.
pub(super) fn publish(out: &Path, files: &[(&str, Vec<u8>)]) -> Result<(), String> {
    let name = out.file_name().ok_or("必须指定具体报表目录")?;
    let parent = out
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let parent = fs::canonicalize(parent).map_err(|e| e.to_string())?;
    let out = parent.join(name);
    if inspect(&out, files)? == Some(Existing::Complete) {
        return Ok(());
    }
    let prefix = format!(".{}.stratide-", name.to_string_lossy());
    let staging = tempfile::Builder::new()
        .prefix(&prefix)
        .tempdir_in(&parent)
        .map_err(|e| e.to_string())?;
    for (name, bytes) in files {
        write_file(&staging.path().join(name), bytes)
            .map_err(|e| format!("写入暂存报表 {name} 失败：{e}"))?;
    }
    if inspect(staging.path(), files)? != Some(Existing::Complete) {
        return Err("暂存报表未完整校验，禁止发布".into());
    }
    fault("before_publish");
    // Recheck immediately before publication: another account may have used the
    // same output path while these derived files were being generated.
    match inspect(&out, files)? {
        Some(Existing::Complete) => return Ok(()),
        Some(Existing::Interrupted) => {
            let archive = parent.join(format!(
                "{}.interrupted",
                staging.path().file_name().unwrap().to_string_lossy()
            ));
            fs::rename(&out, &archive).map_err(|e| format!("归档中断报表失败，原目录保留：{e}"))?;
            eprintln!("已保留中断报表：{}", archive.display());
            fault("after_archive");
        }
        None => {}
    }
    fs::rename(staging.path(), &out).map_err(|e| format!("报表发布未完成，可用原命令重试：{e}"))?;
    fault("after_publish");
    Ok(())
}

#[cfg(not(test))]
fn fault(_: &str) {}

#[cfg(test)]
fn fault(point: &str) {
    if std::env::var("STRATIDE_REPORT_TEST_POINT").as_deref() == Ok(point) {
        std::process::exit(86);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn files() -> Vec<(&'static str, Vec<u8>)> {
        [
            "events.json",
            "daily.csv",
            "orders.csv",
            "fills.csv",
            "positions.csv",
            "report.json",
        ]
        .into_iter()
        .map(|name| (name, format!("complete content: {name}\n").into_bytes()))
        .collect()
    }

    #[test]
    fn crash_child() {
        let Ok(root) = std::env::var("STRATIDE_REPORT_TEST_ROOT") else {
            return;
        };
        publish(&Path::new(&root).join("report"), &files()).unwrap();
    }

    #[test]
    fn process_death_during_write_archive_and_publish_can_resume_same_path() {
        for point in [
            "partial_file",
            "before_publish",
            "after_archive",
            "after_publish",
        ] {
            let temp = tempfile::tempdir().unwrap();
            let out = temp.path().join("report");
            if point == "after_archive" {
                fs::create_dir(&out).unwrap();
                fs::write(out.join("events.json"), &files()[0].1).unwrap();
                fs::write(out.join("daily.csv"), []).unwrap();
            }
            let output = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "replay::report::publish::tests::crash_child",
                    "--nocapture",
                ])
                .env("STRATIDE_REPORT_TEST_ROOT", temp.path())
                .env("STRATIDE_REPORT_TEST_POINT", point)
                .output()
                .unwrap();
            assert_eq!(output.status.code(), Some(86), "point {point}: {output:?}");
            assert_eq!(out.exists(), point == "after_publish", "point {point}");
            publish(&out, &files()).unwrap();
            for (name, expected) in files() {
                assert_eq!(fs::read(out.join(name)).unwrap(), expected);
            }
        }
    }

    #[test]
    fn conflicting_or_nonsequential_content_is_never_archived_or_overwritten() {
        for (name, content) in [
            ("events.json", b"different evidence".as_slice()),
            ("daily.csv", b""),
        ] {
            let temp = tempfile::tempdir().unwrap();
            let out = temp.path().join("report");
            fs::create_dir(&out).unwrap();
            fs::write(out.join(name), content).unwrap();
            assert!(publish(&out, &files()).is_err());
            assert_eq!(fs::read(out.join(name)).unwrap(), content);
            assert_eq!(fs::read_dir(temp.path()).unwrap().count(), 1);
        }
    }
}

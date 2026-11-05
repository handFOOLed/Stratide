//! Per-user logon autostart. Task Scheduler is preferred; a current-user
//! HKCU Run value is the fallback when the task service is unavailable.
//! Neither mechanism requires administrator rights or a Windows service.
use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command;

const RUN_KEY: &str = "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run";

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AutostartStatus {
    pub task_name: String,
    pub exists: bool,
    pub enabled: bool,
    pub mechanism: String,
    pub detail: String,
}

pub fn status() -> AutostartStatus {
    let task = task_status();
    if task.exists {
        return task;
    }
    if run_key_present() {
        return AutostartStatus {
            task_name: crate::SUPERVISOR_TASK.to_string(),
            exists: true,
            enabled: true,
            mechanism: "RUN_KEY".into(),
            detail: "CURRENT_USER_RUN_KEY".into(),
        };
    }
    AutostartStatus {
        task_name: crate::SUPERVISOR_TASK.to_string(),
        exists: false,
        enabled: false,
        mechanism: "NONE".into(),
        detail: task.detail,
    }
}

pub fn set_enabled(launcher: &Path, enabled: bool) -> Result<AutostartStatus, String> {
    let current = status();
    if current.exists && current.mechanism == "TASK_SCHEDULER" {
        let flag = if enabled { "/ENABLE" } else { "/DISABLE" };
        let (code, _, stderr) = schtasks(&["/Change", "/TN", crate::SUPERVISOR_TASK, flag])?;
        if code != 0 {
            return Err(format!("AUTOSTART_CHANGE_FAILED {}", first_line(&stderr)));
        }
        return Ok(status());
    }
    if current.exists && current.mechanism == "RUN_KEY" {
        if enabled {
            return Ok(current);
        }
        let (code, _, stderr) = reg(&["delete", RUN_KEY, "/v", crate::SUPERVISOR_TASK, "/f"])?;
        if code != 0 {
            return Err(format!(
                "AUTOSTART_RUN_KEY_DELETE_FAILED {}",
                first_line(&stderr)
            ));
        }
        return Ok(status());
    }
    if !enabled {
        return Ok(current);
    }
    match create_task(launcher) {
        Ok(()) => Ok(status()),
        Err(task_error) => match write_run_key(launcher) {
            Ok(()) => Ok(status()),
            Err(run_error) => Err(format!(
                "AUTOSTART_UNAVAILABLE task={task_error} run={run_error}"
            )),
        },
    }
}

pub fn remove() -> Result<AutostartStatus, String> {
    if task_status().exists {
        let (code, _, stderr) = schtasks(&["/Delete", "/TN", crate::SUPERVISOR_TASK, "/F"])?;
        if code != 0 {
            return Err(format!("AUTOSTART_DELETE_FAILED {}", first_line(&stderr)));
        }
    }
    if run_key_present() {
        let (code, _, stderr) = reg(&["delete", RUN_KEY, "/v", crate::SUPERVISOR_TASK, "/f"])?;
        if code != 0 {
            return Err(format!(
                "AUTOSTART_RUN_KEY_DELETE_FAILED {}",
                first_line(&stderr)
            ));
        }
    }
    Ok(status())
}

fn create_task(launcher: &Path) -> Result<(), String> {
    let xml = task_xml(launcher)?;
    let path = std::env::temp_dir().join(format!("stratide-autostart-{}.xml", std::process::id()));
    let mut bytes = Vec::with_capacity(xml.len() * 2 + 2);
    bytes.extend_from_slice(&[0xFF, 0xFE]);
    for unit in xml.encode_utf16() {
        bytes.extend_from_slice(&unit.to_le_bytes());
    }
    std::fs::write(&path, bytes).map_err(|error| format!("AUTOSTART_XML_WRITE: {error}"))?;
    let path_text = path.to_string_lossy().to_string();
    let result = schtasks(&[
        "/Create",
        "/TN",
        crate::SUPERVISOR_TASK,
        "/XML",
        &path_text,
        "/F",
    ]);
    let _ = std::fs::remove_file(&path);
    let (code, _, stderr) = result?;
    if code != 0 {
        return Err(format!("AUTOSTART_CREATE_FAILED {}", first_line(&stderr)));
    }
    Ok(())
}

fn task_status() -> AutostartStatus {
    match schtasks(&["/Query", "/TN", crate::SUPERVISOR_TASK, "/XML"]) {
        Ok((0, stdout, _)) => {
            let xml = crate::win::decode_output(&stdout);
            AutostartStatus {
                task_name: crate::SUPERVISOR_TASK.to_string(),
                exists: true,
                enabled: trigger_enabled(&xml).unwrap_or(false),
                mechanism: "TASK_SCHEDULER".into(),
                detail: "TASK_FOUND".into(),
            }
        }
        Ok((code, _, stderr)) => AutostartStatus {
            task_name: crate::SUPERVISOR_TASK.to_string(),
            exists: false,
            enabled: false,
            mechanism: "NONE".into(),
            detail: format!(
                "TASK_NOT_FOUND (schtasks exit {code}) {}",
                first_line(&stderr)
            ),
        },
        Err(error) => AutostartStatus {
            task_name: crate::SUPERVISOR_TASK.to_string(),
            exists: false,
            enabled: false,
            mechanism: "NONE".into(),
            detail: error,
        },
    }
}

fn run_key_present() -> bool {
    match reg(&["query", RUN_KEY, "/v", crate::SUPERVISOR_TASK]) {
        Ok((0, _, _)) => true,
        _ => false,
    }
}

fn write_run_key(launcher: &Path) -> Result<(), String> {
    let value = format!("\"{}\" --background", launcher.to_string_lossy());
    let (code, _, stderr) = reg(&[
        "add",
        RUN_KEY,
        "/v",
        crate::SUPERVISOR_TASK,
        "/t",
        "REG_SZ",
        "/d",
        &value,
        "/f",
    ])?;
    if code != 0 {
        return Err(format!("RUN_KEY_WRITE_FAILED {}", first_line(&stderr)));
    }
    Ok(())
}

fn schtasks(args: &[&str]) -> Result<(i32, Vec<u8>, Vec<u8>), String> {
    run("schtasks.exe", args)
}

fn reg(args: &[&str]) -> Result<(i32, Vec<u8>, Vec<u8>), String> {
    run("reg.exe", args)
}

fn run(program: &str, args: &[&str]) -> Result<(i32, Vec<u8>, Vec<u8>), String> {
    let mut command = Command::new(program);
    command.args(args);
    let (code, stdout, stderr) = crate::run_capture(command, std::time::Duration::from_secs(15))?;
    Ok((code.unwrap_or(-1), stdout, stderr))
}

fn first_line(bytes: &[u8]) -> String {
    crate::win::decode_output(bytes)
        .lines()
        .next()
        .unwrap_or("")
        .trim()
        .chars()
        .take(160)
        .collect()
}

fn trigger_enabled(xml: &str) -> Option<bool> {
    let start = xml.find("<LogonTrigger>")?;
    let end = xml[start..].find("</LogonTrigger>")? + start;
    let trigger = &xml[start..end];
    if trigger.contains("<Enabled>false</Enabled>") {
        Some(false)
    } else {
        // Task Scheduler omits <Enabled> when the trigger is enabled; an
        // exported task that keeps the element but is enabled also lands here.
        Some(true)
    }
}

fn task_xml(launcher: &Path) -> Result<String, String> {
    let domain = std::env::var("USERDOMAIN").map_err(|_| "WINDOWS_USER_IDENTITY_UNAVAILABLE")?;
    let user = std::env::var("USERNAME").map_err(|_| "WINDOWS_USER_IDENTITY_UNAVAILABLE")?;
    let account = format!("{domain}\\{user}");
    let exe = escape_xml(&launcher.to_string_lossy());
    let working = escape_xml(
        &launcher
            .parent()
            .ok_or("LAUNCHER_DIRECTORY_UNAVAILABLE")?
            .to_string_lossy(),
    );
    let account = escape_xml(&account);
    Ok(format!(
        r#"<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Stratide local Paper service (user logon)</Description>
    <URI>\Stratide</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
      <UserId>{account}</UserId>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>{account}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{exe}</Command>
      <Arguments>--background</Arguments>
      <WorkingDirectory>{working}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"#
    ))
}

fn escape_xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}
#[cfg(test)]
mod autostart_tests {
    use super::*;

    #[test]
    fn logon_trigger_state_is_read_from_the_trigger_only() {
        let enabled = "<Task><Settings><Enabled>false</Enabled></Settings><Triggers><LogonTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></LogonTrigger></Triggers></Task>";
        assert_eq!(trigger_enabled(enabled), Some(true));
        let disabled = "<Triggers><LogonTrigger><Enabled>false</Enabled></LogonTrigger></Triggers><Settings><Enabled>true</Enabled></Settings>";
        assert_eq!(trigger_enabled(disabled), Some(false));
        // schtasks /Query /XML omits the element for a normal enabled trigger.
        let normalized =
            "<Triggers><LogonTrigger><Delay>PT30S</Delay></LogonTrigger></Triggers><Settings><Enabled>true</Enabled></Settings>";
        assert_eq!(trigger_enabled(normalized), Some(true));
        assert_eq!(trigger_enabled("<Task></Task>"), None);
    }

    #[test]
    fn task_xml_is_a_single_login_trigger_with_least_privilege() {
        let xml = task_xml(std::path::Path::new(
            "C:\\Program Files\\Stratide\\stratide-launcher.exe",
        ))
        .expect("xml");
        assert!(xml.contains("<LogonTrigger>"));
        assert_eq!(xml.matches("<LogonTrigger>").count(), 1);
        assert!(xml.contains("<RunLevel>LeastPrivilege</RunLevel>"));
        assert!(xml.contains("<Arguments>--background</Arguments>"));
        assert!(xml.contains("<UserId>"));
        assert!(
            xml.contains("<Command>C:\\Program Files\\Stratide\\stratide-launcher.exe</Command>")
        );
    }

    #[test]
    fn xml_escape_covers_attribute_and_text_characters() {
        assert_eq!(escape_xml("a&b<c>\"d'e"), "a&amp;b&lt;c&gt;&quot;d&apos;e");
    }

    #[test]
    fn status_has_a_stable_contract_when_no_mechanism_exists() {
        let value = serde_json::to_value(AutostartStatus {
            task_name: "Stratide".into(),
            exists: false,
            enabled: false,
            mechanism: "NONE".into(),
            detail: "TASK_NOT_FOUND".into(),
        })
        .expect("json");
        assert_eq!(value["mechanism"], "NONE");
        assert_eq!(value["enabled"], false);
    }
}

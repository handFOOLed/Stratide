use serde::Deserialize;
use std::io::{Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

#[derive(Clone, Debug, Deserialize)]
pub struct HealthData {
    pub service: String,
    pub paper_only: bool,
    pub process_id: String,
    pub instance_id: String,
    #[serde(default)]
    pub agent: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProbeError {
    Refused,
    Timeout,
    NotStratide,
    Invalid,
}

impl ProbeError {
    pub fn code(self) -> &'static str {
        match self {
            Self::Refused => "SERVICE_NOT_RUNNING",
            Self::Timeout => "SERVICE_HEALTH_TIMEOUT",
            Self::NotStratide => "PORT_IN_USE_BY_OTHER_APPLICATION",
            Self::Invalid => "SERVICE_HEALTH_INVALID",
        }
    }
}

/// True when no local listener owns the port. Used to distinguish "not started
/// yet" from "another application already owns this port" without killing PIDs.
pub fn port_available(port: u16) -> bool {
    std::net::TcpListener::bind(("127.0.0.1", port)).is_ok()
}

#[derive(Deserialize)]
struct Envelope {
    data: HealthData,
}

pub fn probe(port: u16) -> Result<HealthData, ProbeError> {
    let address = format!("127.0.0.1:{port}");
    let socket = address
        .to_socket_addrs()
        .map_err(|_| ProbeError::Invalid)?
        .next()
        .ok_or(ProbeError::Invalid)?;
    let mut stream = match TcpStream::connect_timeout(&socket, Duration::from_millis(1500)) {
        Ok(stream) => stream,
        Err(error) => {
            return Err(match error.kind() {
                std::io::ErrorKind::TimedOut => ProbeError::Timeout,
                _ => ProbeError::Refused,
            })
        }
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let request = format!(
        "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\nAccept: application/json\r\n\r\n"
    );
    if stream.write_all(request.as_bytes()).is_err() {
        return Err(ProbeError::NotStratide);
    }
    let mut buffer = Vec::new();
    let _ = stream.take(256 * 1024).read_to_end(&mut buffer);
    let split = buffer
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or(ProbeError::NotStratide)?;
    let head = String::from_utf8_lossy(&buffer[..split]);
    if !head.starts_with("HTTP/1.") || !head.contains(" 200 ") {
        return Err(ProbeError::NotStratide);
    }
    let envelope: Envelope =
        serde_json::from_slice(&buffer[split + 4..]).map_err(|_| ProbeError::NotStratide)?;
    if envelope.data.service != "online"
        || envelope.data.process_id.is_empty()
        || envelope.data.instance_id.is_empty()
    {
        return Err(ProbeError::Invalid);
    }
    Ok(envelope.data)
}

/// Ask a managed local service to exit through its loopback-only runtime
/// endpoint. Used only after the supervisor has decided to stop.
pub fn request_shutdown(port: u16) -> Result<(), ProbeError> {
    let address = format!("127.0.0.1:{port}");
    let socket = address
        .to_socket_addrs()
        .map_err(|_| ProbeError::Invalid)?
        .next()
        .ok_or(ProbeError::Invalid)?;
    let mut stream = TcpStream::connect_timeout(&socket, Duration::from_millis(800))
        .map_err(|_| ProbeError::Refused)?;
    let _ = stream.set_read_timeout(Some(Duration::from_secs(3)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(3)));
    let body = b"{}";
    let request = format!(
        "POST /api/runtime/shutdown HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nOrigin: http://127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
        body.len()
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|_| ProbeError::NotStratide)?;
    stream
        .write_all(body)
        .map_err(|_| ProbeError::NotStratide)?;
    let mut buffer = Vec::new();
    let _ = stream.take(64 * 1024).read_to_end(&mut buffer);
    let head = String::from_utf8_lossy(&buffer);
    if head.starts_with("HTTP/1.") && head.contains(" 200 ") {
        Ok(())
    } else {
        Err(ProbeError::NotStratide)
    }
}

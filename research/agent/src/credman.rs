//! Windows Credential Manager for the Owner's cloud research key.
//!
//! The secret is written to the current user's credential vault; it never enters
//! a file, argv, environment variable, log or HTTP response.
use crate::Result;
use zeroize::Zeroizing;

#[cfg(windows)]
mod win {
    use super::*;
    use std::{ffi::c_void, ptr};

    const CRED_TYPE_GENERIC: u32 = 1;
    const CRED_PERSIST_LOCAL_MACHINE: u32 = 2;

    #[repr(C)]
    struct FileTime {
        low: u32,
        high: u32,
    }

    #[repr(C)]
    struct Credential {
        flags: u32,
        kind: u32,
        target_name: *mut u16,
        comment: *mut u16,
        last_written: FileTime,
        blob_size: u32,
        blob: *mut u8,
        persist: u32,
        attribute_count: u32,
        attributes: *mut c_void,
        target_alias: *mut u16,
        user_name: *mut u16,
    }

    #[link(name = "Advapi32")]
    extern "system" {
        fn CredWriteW(credential: *const Credential, flags: u32) -> i32;
        fn CredReadW(target: *const u16, kind: u32, flags: u32, out: *mut *mut Credential) -> i32;
        fn CredDeleteW(target: *const u16, kind: u32, flags: u32) -> i32;
        fn CredFree(buffer: *mut c_void);
    }

    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain([0]).collect()
    }

    pub fn write(target: &str, user: &str, secret: &str) -> Result<()> {
        let mut target = wide(target);
        let mut user = wide(user);
        let mut blob: Vec<u8> = secret.encode_utf16().flat_map(u16::to_le_bytes).collect();
        let entry = Credential {
            flags: 0,
            kind: CRED_TYPE_GENERIC,
            target_name: target.as_mut_ptr(),
            comment: ptr::null_mut(),
            last_written: FileTime { low: 0, high: 0 },
            blob_size: blob.len() as u32,
            blob: blob.as_mut_ptr(),
            persist: CRED_PERSIST_LOCAL_MACHINE,
            attribute_count: 0,
            attributes: ptr::null_mut(),
            target_alias: ptr::null_mut(),
            user_name: user.as_mut_ptr(),
        };
        let ok = unsafe { CredWriteW(&entry, 0) };
        blob.fill(0);
        crate::ensure(ok != 0, "CREDENTIAL_WRITE_FAILED")
    }

    fn read_raw(target: &str) -> Result<Vec<u8>> {
        let target = wide(target);
        let mut out: *mut Credential = ptr::null_mut();
        let ok = unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut out) };
        crate::ensure(ok != 0 && !out.is_null(), "CREDENTIAL_NOT_FOUND")?;
        let mut bytes = Vec::new();
        unsafe {
            let entry = &*out;
            if !entry.blob.is_null() && entry.blob_size > 0 {
                bytes.extend_from_slice(std::slice::from_raw_parts(
                    entry.blob,
                    entry.blob_size as usize,
                ));
            }
            CredFree(out as *mut c_void);
        }
        Ok(bytes)
    }

    pub fn read(target: &str) -> Result<Zeroizing<String>> {
        let bytes = read_raw(target)?;
        crate::ensure(bytes.len() % 2 == 0, "CREDENTIAL_INVALID")?;
        let units: Vec<u16> = bytes
            .chunks_exact(2)
            .map(|pair| u16::from_le_bytes([pair[0], pair[1]]))
            .collect();
        String::from_utf16(&units)
            .map(Zeroizing::new)
            .map_err(|_| "CREDENTIAL_INVALID".into())
    }

    pub fn exists(target: &str) -> bool {
        let target = wide(target);
        let mut entry: *mut Credential = ptr::null_mut();
        let ok = unsafe { CredReadW(target.as_ptr(), CRED_TYPE_GENERIC, 0, &mut entry) };
        if ok == 0 || entry.is_null() {
            return false;
        }
        unsafe { CredFree(entry.cast()) };
        true
    }

    pub fn delete(target: &str) -> Result<()> {
        if !exists(target) {
            return Ok(());
        }
        let target = wide(target);
        let ok = unsafe { CredDeleteW(target.as_ptr(), CRED_TYPE_GENERIC, 0) };
        crate::ensure(ok != 0, "CREDENTIAL_DELETE_FAILED")
    }
}

#[cfg(windows)]
pub use win::{delete, exists, read, write};

#[cfg(not(windows))]
pub fn write(_target: &str, _user: &str, _secret: &str) -> Result<()> {
    Err("CREDENTIAL_MANAGER_REQUIRES_WINDOWS".into())
}

#[cfg(not(windows))]
pub fn read(_target: &str) -> Result<Zeroizing<String>> {
    Err("CREDENTIAL_MANAGER_REQUIRES_WINDOWS".into())
}

#[cfg(not(windows))]
pub fn exists(_target: &str) -> bool {
    false
}

#[cfg(not(windows))]
pub fn delete(_target: &str) -> Result<()> {
    Err("CREDENTIAL_MANAGER_REQUIRES_WINDOWS".into())
}

#[cfg(all(test, windows))]
mod tests {
    use super::*;

    #[test]
    fn round_trip_and_delete() {
        let target = format!("Stratide/test/{}", crate::nonce().unwrap());
        assert!(!exists(&target));
        write(&target, "Stratide test", "sk-test-0123456789abcdefghij").unwrap();
        assert!(exists(&target));
        assert_eq!(
            read(&target).unwrap().as_str(),
            "sk-test-0123456789abcdefghij"
        );
        delete(&target).unwrap();
        assert!(!exists(&target));
        delete(&target).unwrap();
    }
}

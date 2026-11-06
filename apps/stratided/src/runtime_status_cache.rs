//! Cached `/api/runtime/status` payload with epoch guards against stale background refresh.
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

static STATUS_EPOCH: AtomicU64 = AtomicU64::new(0);
static STATUS_CACHE: Mutex<Option<StatusCacheState>> = Mutex::new(None);
static STATUS_REFRESHING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

pub const STALE_AFTER: Duration = Duration::from_secs(4);
pub const SERVE_MAX_AGE: Duration = Duration::from_secs(120);

struct StatusCacheState {
    value: Value,
    built_at: Instant,
    epoch: u64,
}

pub fn epoch() -> u64 {
    STATUS_EPOCH.load(Ordering::Acquire)
}

/// Invalidate in-flight background collectors; call before dependency mutations.
pub fn bump_epoch() -> u64 {
    STATUS_EPOCH.fetch_add(1, Ordering::AcqRel) + 1
}

pub fn invalidate_cache() {
    bump_epoch();
    if let Ok(mut cache) = STATUS_CACHE.lock() {
        *cache = None;
    }
}

pub fn cached_value(max_age: Duration) -> Option<Value> {
    let cache = STATUS_CACHE.lock().ok()?;
    let entry = cache.as_ref()?;
    if entry.built_at.elapsed() > max_age {
        return None;
    }
    Some(entry.value.clone())
}

pub fn publish_if_current(value: Value, captured_epoch: u64) -> bool {
    if epoch() != captured_epoch {
        return false;
    }
    if let Ok(mut cache) = STATUS_CACHE.lock() {
        if epoch() != captured_epoch {
            return false;
        }
        *cache = Some(StatusCacheState {
            value,
            built_at: Instant::now(),
            epoch: captured_epoch,
        });
        return true;
    }
    false
}

pub fn publish(value: Value) {
    let current = epoch();
    let _ = publish_if_current(value, current);
}

pub fn should_refresh_background() -> bool {
    let stale = STATUS_CACHE
        .lock()
        .ok()
        .and_then(|cache| {
            cache
                .as_ref()
                .map(|entry| entry.built_at.elapsed() > STALE_AFTER)
        })
        .unwrap_or(true);
    stale
}

pub fn try_begin_background_refresh() -> bool {
    if !should_refresh_background() {
        return false;
    }
    STATUS_REFRESHING
        .compare_exchange(false, true, Ordering::Acquire, Ordering::Relaxed)
        .is_ok()
}

pub fn end_background_refresh() {
    STATUS_REFRESHING.store(false, Ordering::Release);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stale_epoch_refresh_cannot_overwrite_newer_cache() {
        invalidate_cache();
        let old_epoch = epoch();
        publish_if_current(serde_json::json!({"generation": "old"}), old_epoch);
        bump_epoch();
        assert!(!publish_if_current(
            serde_json::json!({"generation": "stale-background"}),
            old_epoch
        ));
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["generation"], "old");
        bump_epoch();
        publish_if_current(serde_json::json!({"generation": "new"}), epoch());
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["generation"], "new");
    }
}

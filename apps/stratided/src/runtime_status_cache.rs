//! Cached `/api/runtime/status` payload with epoch + generation guards.
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

static STATUS_EPOCH: AtomicU64 = AtomicU64::new(0);
static STATUS_GENERATION: AtomicU64 = AtomicU64::new(0);
static STATUS_CACHE: Mutex<Option<StatusCacheState>> = Mutex::new(None);
static STATUS_REFRESHING: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(false);

pub const STALE_AFTER: Duration = Duration::from_secs(4);
pub const SERVE_MAX_AGE: Duration = Duration::from_secs(120);

struct StatusCacheState {
    value: Value,
    built_at: Instant,
    #[allow(dead_code)]
    epoch: u64,
    #[allow(dead_code)]
    generation: u64,
}

pub fn epoch() -> u64 {
    STATUS_EPOCH.load(Ordering::Acquire)
}

pub fn generation() -> u64 {
    STATUS_GENERATION.load(Ordering::Acquire)
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

fn store_locked(cache: &mut Option<StatusCacheState>, value: Value, epoch: u64, generation: u64) {
    *cache = Some(StatusCacheState {
        value,
        built_at: Instant::now(),
        epoch,
        generation,
    });
}

/// Publish only if no newer snapshot was written since `generation_at_start`.
pub fn publish_if_not_superseded(
    value: Value,
    captured_epoch: u64,
    generation_at_start: u64,
) -> bool {
    if epoch() != captured_epoch {
        return false;
    }
    if generation() > generation_at_start {
        return false;
    }
    if let Ok(mut cache) = STATUS_CACHE.lock() {
        if epoch() != captured_epoch {
            return false;
        }
        if generation() > generation_at_start {
            return false;
        }
        let next_generation = STATUS_GENERATION.fetch_add(1, Ordering::AcqRel) + 1;
        if epoch() != captured_epoch {
            return false;
        }
        store_locked(&mut cache, value, captured_epoch, next_generation);
        return true;
    }
    false
}

pub fn publish(value: Value) {
    let current_epoch = epoch();
    let next_generation = STATUS_GENERATION.fetch_add(1, Ordering::AcqRel) + 1;
    if let Ok(mut cache) = STATUS_CACHE.lock() {
        store_locked(&mut cache, value, current_epoch, next_generation);
    }
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

pub fn try_begin_background_refresh(force: bool) -> bool {
    if !force && !should_refresh_background() {
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

    fn reset_test_state() {
        STATUS_EPOCH.store(0, Ordering::Release);
        STATUS_GENERATION.store(0, Ordering::Release);
        STATUS_REFRESHING.store(false, Ordering::Release);
        if let Ok(mut cache) = STATUS_CACHE.lock() {
            *cache = None;
        }
    }

    #[test]
    fn stale_epoch_refresh_cannot_overwrite_newer_cache() {
        reset_test_state();
        let old_epoch = epoch();
        publish_if_not_superseded(serde_json::json!({"generation": "old"}), old_epoch, 0);
        bump_epoch();
        assert!(!publish_if_not_superseded(
            serde_json::json!({"generation": "stale-background"}),
            old_epoch,
            0
        ));
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["generation"], "old");
        bump_epoch();
        publish(serde_json::json!({"generation": "new"}));
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["generation"], "new");
    }

    #[test]
    fn same_epoch_probe_snapshot_not_replaced_by_earlier_refresh() {
        reset_test_state();
        let current_epoch = epoch();
        let gen_start = generation();
        publish(serde_json::json!({
            "dependencies": {"timesfm": {"state": "READY", "reason": null}}
        }));
        assert!(!publish_if_not_superseded(
            serde_json::json!({
                "dependencies": {"timesfm": {"state": "CONFIGURED", "reason": "WSL_PROBE_REQUIRED"}}
            }),
            current_epoch,
            gen_start
        ));
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["dependencies"]["timesfm"]["state"], "READY");
    }

    #[test]
    fn refresh_started_during_mutation_is_dropped_when_generation_advances() {
        reset_test_state();
        let refresh_epoch = epoch();
        let refresh_generation_start = generation();
        bump_epoch();
        publish(serde_json::json!({"marker": "after-mutation"}));
        assert!(!publish_if_not_superseded(
            serde_json::json!({"marker": "stale-full-collect"}),
            refresh_epoch,
            refresh_generation_start
        ));
        let cached = cached_value(SERVE_MAX_AGE).expect("cache");
        assert_eq!(cached["marker"], "after-mutation");
    }
}

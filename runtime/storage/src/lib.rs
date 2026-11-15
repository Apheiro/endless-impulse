//! Linux metadata-only storage scanner and bounded JSON Lines protocol.
#[cfg(not(target_os = "linux"))]
compile_error!("endless-storage requires Linux");
pub mod ipc;
pub mod scan;

//! Linux descriptor-relative I/O. Never follow a destination or source symlink.
use crate::{Error, Result, digest, relative};
use serde::{Deserialize, Serialize};
use std::ffi::CString;
use std::fs::File;
use std::io::{Read, Write};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path};
use std::sync::atomic::{AtomicU64, Ordering};

pub(crate) const MAX_FILE: usize = 4 * 1024 * 1024;
const MAX_STATE: usize = 64 * 1024 * 1024;
static TEMP: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Image {
    pub bytes: Vec<u8>,
    pub mode: u32,
}
impl Image {
    pub fn sha(&self) -> String {
        digest(&self.bytes)
    }
}

pub(crate) struct Dir(File, bool);
// Linux openat2 ABI, from linux/openat2.h. Fail closed if the kernel cannot
// enforce BENEATH + NO_SYMLINKS + NO_XDEV (including nested bind mounts).
#[repr(C)]
struct OpenHow {
    flags: u64,
    mode: u64,
    resolve: u64,
}
fn cstring(value: &[u8]) -> Result<CString> {
    CString::new(value).map_err(|_| Error::msg("NUL in path"))
}
fn opened(fd: libc::c_int) -> Result<File> {
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // SAFETY: successful open/openat returned a new, exclusively owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}
impl Dir {
    pub fn absolute(path: &Path) -> Result<Self> {
        if !path.is_absolute() {
            return Err(Error::msg("An absolute path is required"));
        }
        // SAFETY: constant NUL-terminated path, valid open flags, no varargs mode needed.
        let mut dir = Self(
            opened(unsafe {
                libc::open(
                    c"/".as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
                )
            })?,
            false,
        );
        for part in path.components() {
            match part {
                Component::RootDir => {}
                Component::Normal(name) => {
                    dir = dir.child(name.as_bytes(), false)?;
                }
                _ => return Err(Error::msg("Non-normal path component")),
            }
        }
        Ok(dir)
    }
    pub fn confined(mut self) -> Result<Self> {
        self.1 = true;
        self.open_leaf(
            c".",
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
            0,
        )?;
        Ok(self)
    }
    pub fn below(&self, relative: &Path) -> Result<Self> {
        let mut dir = Self(self.0.try_clone()?, self.1);
        for component in relative.components() {
            let Component::Normal(name) = component else {
                return Err(Error::msg("Invalid sandbox component"));
            };
            dir = dir.child(name.as_bytes(), false)?;
        }
        Ok(dir)
    }
    fn open_leaf(&self, name: &std::ffi::CStr, flags: i32, mode: u32) -> Result<File> {
        if self.1 {
            let how = OpenHow {
                flags: flags as u64,
                mode: mode as u64,
                resolve: 0x01 | 0x04 | 0x08,
            };
            // SAFETY: valid held dirfd, NUL-terminated one-component name and
            // correctly sized Linux open_how. The returned descriptor is owned.
            let fd = unsafe {
                libc::syscall(
                    libc::SYS_openat2,
                    self.0.as_raw_fd(),
                    name.as_ptr(),
                    &how,
                    std::mem::size_of::<OpenHow>(),
                )
            };
            if fd < 0 && std::io::Error::last_os_error().raw_os_error() == Some(libc::ENOSYS) {
                return Err(Error::msg(
                    "Linux openat2 is required for sandbox confinement (kernel >= 5.6)",
                ));
            }
            opened(fd as i32)
        } else {
            // SAFETY: one component, valid flags/mode; O_NOFOLLOW is supplied by callers.
            opened(unsafe { libc::openat(self.0.as_raw_fd(), name.as_ptr(), flags, mode) })
        }
    }
    fn child(&self, name: &[u8], create: bool) -> Result<Self> {
        let name = cstring(name)?;
        if create {
            // SAFETY: descriptor and C path are valid; mode has no special bits.
            let result = unsafe { libc::mkdirat(self.0.as_raw_fd(), name.as_ptr(), 0o700) };
            if result != 0 && std::io::Error::last_os_error().raw_os_error() != Some(libc::EEXIST) {
                return Err(std::io::Error::last_os_error().into());
            }
            self.0.sync_all()?;
        }
        Ok(Self(
            self.open_leaf(
                &name,
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0,
            )?,
            self.1,
        ))
    }
    fn parent(&self, path: &str, create: bool) -> Result<(Self, CString)> {
        relative(path)?;
        let mut parts: Vec<_> = path.split('/').collect();
        let leaf = cstring(parts.pop().expect("validated path").as_bytes())?;
        let mut dir = Self(self.0.try_clone()?, self.1);
        for part in parts {
            dir = dir.child(part.as_bytes(), create)?;
        }
        Ok((dir, leaf))
    }
    pub fn metadata(&self) -> Result<std::fs::Metadata> {
        Ok(self.0.metadata()?)
    }
    pub fn read(&self, path: &str) -> Result<Option<Image>> {
        let (parent, leaf) = match self.parent(path, false) {
            Ok(value) => value,
            Err(Error::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e),
        };
        // NONBLOCK prevents FIFO/device hangs before the regular-file check.
        let file = parent.open_leaf(
            &leaf,
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC,
            0,
        );
        let mut file = match file {
            Ok(file) => file,
            Err(Error::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(e) => return Err(e),
        };
        let meta = file.metadata()?;
        if !meta.is_file() || meta.nlink() != 1 {
            return Err(Error::msg(format!(
                "Not a single-link regular file: {path}"
            )));
        }
        if meta.mode() & 0o7000 != 0 {
            return Err(Error::msg(format!(
                "Special file permission bits are unsupported: {path}"
            )));
        }
        let limit = if path.starts_with(".endless-setup/") {
            MAX_STATE
        } else {
            MAX_FILE
        };
        if meta.len() > limit as u64 {
            return Err(Error::msg("File exceeds safety limit"));
        }
        let mut bytes = Vec::new();
        Read::by_ref(&mut file)
            .take(limit as u64 + 1)
            .read_to_end(&mut bytes)?;
        if bytes.len() > limit {
            return Err(Error::msg("File grew beyond safety limit"));
        }
        Ok(Some(Image {
            bytes,
            mode: meta.mode() & 0o777,
        }))
    }
    pub fn replace(
        &self,
        path: &str,
        expected: &Option<Image>,
        next: &Option<Image>,
    ) -> Result<()> {
        if self.read(path)? != *expected {
            return Err(Error::msg(format!("Concurrent change: {path}")));
        }
        if expected == next {
            return Ok(());
        }
        let (parent, leaf) = self.parent(path, next.is_some())?;
        if let Some(next) = next {
            let name = format!(
                ".endless-setup-tmp-{}-{}",
                std::process::id(),
                TEMP.fetch_add(1, Ordering::Relaxed)
            );
            let temporary = cstring(name.as_bytes())?;
            let mut file = parent.open_leaf(
                &temporary,
                libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0o600,
            )?;
            let result = (|| -> Result<()> {
                file.write_all(&next.bytes)?;
                // SAFETY: valid owned descriptor, validated permission bits only.
                if unsafe { libc::fchmod(file.as_raw_fd(), next.mode) } != 0 {
                    return Err(std::io::Error::last_os_error().into());
                }
                file.sync_all()?;
                if self.read(path)? != *expected {
                    return Err(Error::msg(format!("Concurrent change: {path}")));
                }
                // SAFETY: atomic replacement of a directory entry; destination links are not followed.
                if unsafe {
                    libc::renameat(
                        parent.0.as_raw_fd(),
                        temporary.as_ptr(),
                        parent.0.as_raw_fd(),
                        leaf.as_ptr(),
                    )
                } != 0
                {
                    return Err(std::io::Error::last_os_error().into());
                }
                parent.0.sync_all()?;
                Ok(())
            })();
            if result.is_err() {
                // SAFETY: only this operation's exclusively created temporary file, never a directory.
                unsafe {
                    libc::unlinkat(parent.0.as_raw_fd(), temporary.as_ptr(), 0);
                }
            }
            result
        } else {
            // SAFETY: unlink a single leaf, flags=0 refuses directories; no recursive deletion.
            if unsafe { libc::unlinkat(parent.0.as_raw_fd(), leaf.as_ptr(), 0) } != 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            parent.0.sync_all()?;
            Ok(())
        }
    }
    pub fn lock(&self) -> Result<File> {
        let state = self.child(b".endless-setup", true)?;
        let meta = state.metadata()?;
        // SAFETY: geteuid takes no arguments.
        if meta.uid() != unsafe { libc::geteuid() } || meta.mode() & 0o7777 != 0o700 {
            return Err(Error::msg(
                "State directory must be private and owned by this user",
            ));
        }
        // The persistent execution lock is never unlinked.
        let file = state.open_leaf(
            c"lock",
            libc::O_RDWR | libc::O_CREAT | libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC,
            0o600,
        )?;
        let meta = file.metadata()?;
        if !meta.is_file() || meta.nlink() != 1 || meta.mode() & 0o7777 != 0o600 || meta.len() != 0
        {
            return Err(Error::msg("Unsafe execution lock"));
        }
        // SAFETY: valid file descriptor; advisory nonblocking exclusive lock.
        if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(Error::msg("Another operation holds the sandbox lock"));
        }
        Ok(file)
    }
    pub fn check_state(&self) -> Result<()> {
        let state = match self.child(b".endless-setup", false) {
            Ok(state) => state,
            Err(Error::Io(e)) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(error) => return Err(error),
        };
        let metadata = state.metadata()?;
        // SAFETY: geteuid takes no arguments.
        if metadata.uid() != unsafe { libc::geteuid() } || metadata.mode() & 0o7777 != 0o700 {
            return Err(Error::msg(
                "State directory must be private and owned by this user",
            ));
        }
        Ok(())
    }
}

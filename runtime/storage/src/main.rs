fn main() {
    // Do not print panic payloads, filesystem names or raw OS error messages.
    std::panic::set_hook(Box::new(|_| eprintln!("endless-storage: internal failure")));
    if let Err(error) = endless_storage::ipc::run() {
        if error.kind() != std::io::ErrorKind::BrokenPipe {
            eprintln!("endless-storage: IPC I/O failure");
        }
        std::process::exit(1);
    }
}

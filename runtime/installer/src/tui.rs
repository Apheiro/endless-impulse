//! Small terminal view; all planning and filesystem decisions stay in the core.
//! No TUI crates were cached for this MVP. Raw terminal handling is Linux-only;
//! TERM=dumb uses an accessible numbered view and non-TTY input never waits.
use crate::{Options, pretty};
use endless_setup::{Action, Engine, doctor};
use std::io::{self, IsTerminal, Write};

const ITEMS: [&str; 9] = [
    "Overview",
    "Plan install (read only)",
    "Install subset",
    "Update subset",
    "Repair subset",
    "Uninstall inventoried files",
    "Doctor (read only)",
    "Toggle backup/replacement of preexisting managed files",
    "Exit",
];

struct RawTerminal(libc::termios);

impl RawTerminal {
    fn enter() -> io::Result<Self> {
        // SAFETY: tcgetattr initializes this valid termios pointer; stdin is a TTY.
        let mut original = unsafe { std::mem::zeroed::<libc::termios>() };
        if unsafe { libc::tcgetattr(libc::STDIN_FILENO, &mut original) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let mut raw = original;
        // Handle Ctrl-C/Ctrl-D as keys so RAII restores attributes before exit.
        raw.c_lflag &= !(libc::ICANON | libc::ECHO | libc::ISIG);
        raw.c_cc[libc::VMIN] = 1;
        raw.c_cc[libc::VTIME] = 0;
        // SAFETY: original/raw came from tcgetattr on the same terminal.
        if unsafe { libc::tcsetattr(libc::STDIN_FILENO, libc::TCSANOW, &raw) } != 0 {
            return Err(io::Error::last_os_error());
        }
        Ok(Self(original))
    }
}

impl Drop for RawTerminal {
    fn drop(&mut self) {
        // SAFETY: restore the saved valid attributes even on error/panic.
        unsafe { libc::tcsetattr(libc::STDIN_FILENO, libc::TCSANOW, &self.0) };
    }
}

fn byte_ready() -> io::Result<bool> {
    let mut descriptor = libc::pollfd {
        fd: libc::STDIN_FILENO,
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one initialized pollfd is valid for the duration of this call.
    let result = unsafe { libc::poll(&mut descriptor, 1, 80) };
    if result < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(result > 0)
    }
}

fn raw_byte() -> io::Result<u8> {
    let mut byte = 0_u8;
    loop {
        // SAFETY: one writable byte is valid. Use unbuffered input so poll can
        // detect the remaining bytes of an escape sequence on this descriptor.
        let count = unsafe {
            libc::read(
                libc::STDIN_FILENO,
                (&mut byte as *mut u8).cast::<libc::c_void>(),
                1,
            )
        };
        if count == 1 {
            return Ok(byte);
        }
        if count == 0 {
            return Err(io::Error::new(
                io::ErrorKind::UnexpectedEof,
                "Terminal closed",
            ));
        }
        let error = io::Error::last_os_error();
        if error.kind() != io::ErrorKind::Interrupted {
            return Err(error);
        }
    }
}

fn menu(selected: &mut usize, replace: bool) -> Result<usize, String> {
    let _terminal = RawTerminal::enter().map_err(|e| e.to_string())?;
    loop {
        print!("\x1b[2J\x1b[HEXPERIMENTAL SANDBOX ONLY\nEndless Impulse — subset preview\n\n");
        println!(
            "Preexisting managed files: {}\n",
            if replace {
                "backup then replace (explicit opt-in)"
            } else {
                "block replacement"
            }
        );
        for (index, label) in ITEMS.iter().enumerate() {
            println!("{} {label}", if *selected == index { ">" } else { " " });
        }
        println!("\nUp/Down: select   Enter: inspect/continue   Esc: exit");
        io::stdout().flush().map_err(|e| e.to_string())?;
        let key = raw_byte().map_err(|e| e.to_string())?;
        match key {
            b'\n' | b'\r' => return Ok(*selected),
            27 => {
                if !byte_ready().map_err(|e| e.to_string())? {
                    return Ok(8);
                }
                let key = raw_byte().map_err(|e| e.to_string())?;
                if key == b'[' && byte_ready().map_err(|e| e.to_string())? {
                    match raw_byte().map_err(|e| e.to_string())? {
                        b'A' => *selected = (*selected + ITEMS.len() - 1) % ITEMS.len(),
                        b'B' => *selected = (*selected + 1) % ITEMS.len(),
                        _ => {}
                    }
                } else {
                    return Ok(8);
                }
            }
            b'q' | 3 | 4 => return Ok(8),
            _ => {}
        }
    }
}

fn text_menu(replace: bool) -> Result<usize, String> {
    println!("\nEXPERIMENTAL SANDBOX ONLY — allow replacement: {replace}");
    for (index, label) in ITEMS.iter().enumerate() {
        println!("{}. {label}", index + 1);
    }
    print!("Number (empty or Esc = exit): ");
    io::stdout().flush().map_err(|e| e.to_string())?;
    let mut line = String::new();
    if io::stdin()
        .read_line(&mut line)
        .map_err(|e| e.to_string())?
        == 0
    {
        return Ok(8);
    }
    if line.trim().is_empty() || line.contains('\x1b') {
        return Ok(8);
    }
    let index = line.trim().parse::<usize>().unwrap_or(0);
    if !(1..=ITEMS.len()).contains(&index) {
        return Err("Choose one of the displayed numbers.".into());
    }
    Ok(index - 1)
}

fn overview(options: &Options, replace: bool) {
    println!("EXPERIMENTAL SANDBOX ONLY — desktop installation incomplete");
    println!(
        "Sandbox: {}",
        options
            .sandbox
            .as_deref()
            .map_or_else(|| "<required>".into(), |p| p.display().to_string())
    );
    println!(
        "Manifest: {}",
        options.manifest.as_deref().map_or_else(
            || "<none; uninstall/doctor only>".into(),
            |p| p.display().to_string()
        )
    );
    println!("Backup/replacement opt-in: {replace}");
    println!(
        "Only a representative subset is supported. No dependencies, services, real host configuration, complete installation or existing-Hyprland integration are applied."
    );
    println!(
        "Modified managed files block replacement; uninstall preserves them. Preferences and backups are retained by default."
    );
}

pub(crate) fn run(options: &Options) -> Result<(), String> {
    let root = options
        .sandbox
        .as_deref()
        .ok_or("--sandbox DIR is mandatory for tui.")?;
    let engine = Engine::open(root).map_err(|e| e.to_string())?;
    let mut replace = options.allow_replace;
    overview(options, replace);
    if !io::stdin().is_terminal() || !io::stdout().is_terminal() {
        println!(
            "Non-interactive terminal: no input requested and no changes applied. Use plan --json, then an explicit sandbox command with --yes."
        );
        return Ok(());
    }
    let text_mode = std::env::var("TERM").map_or(true, |term| term == "dumb");
    let mut selected = 0;
    loop {
        let choice = if text_mode {
            text_menu(replace)?
        } else {
            match menu(&mut selected, replace) {
                Ok(choice) => choice,
                Err(error) => {
                    println!("Terminal navigation unavailable ({error}); using text menu.");
                    text_menu(replace)?
                }
            }
        };
        if choice == 8 {
            return Ok(());
        }
        if choice == 7 {
            replace = !replace;
            continue;
        }
        let result = (|| -> Result<(), String> {
            if choice == 0 {
                overview(options, replace);
            } else if choice == 6 {
                let host = doctor(options.manifest.as_deref()).map_err(|e| e.to_string())?;
                let sandbox = engine.inspect().map_err(|e| e.to_string())?;
                println!(
                    "{}",
                    pretty(&serde_json::json!({"host": host, "sandbox": sandbox}))?
                );
            } else {
                let action = match choice {
                    1 | 2 => Action::Install,
                    3 => Action::Update,
                    4 => Action::Repair,
                    5 => Action::Uninstall,
                    _ => unreachable!(),
                };
                let plan = engine
                    .plan(action, options.manifest.as_deref(), replace)
                    .map_err(|e| e.to_string())?;
                println!("{}", pretty(&plan)?);
                if choice != 1 && plan.blocked.is_empty() {
                    print!(
                        "Apply exactly this sandbox plan? Type APPLY SANDBOX (anything else cancels): "
                    );
                    io::stdout().flush().map_err(|e| e.to_string())?;
                    let mut line = String::new();
                    io::stdin()
                        .read_line(&mut line)
                        .map_err(|e| e.to_string())?;
                    if line.trim() == "APPLY SANDBOX" {
                        println!(
                            "{}",
                            pretty(&engine.execute(&plan).map_err(|e| e.to_string())?)?
                        );
                    } else {
                        println!("Cancelled. No changes applied.");
                    }
                } else if !plan.blocked.is_empty() {
                    println!("Plan blocked. No changes applied.");
                }
            }
            Ok(())
        })();
        if let Err(error) = result {
            println!("Operation failed: {error}");
        }
        print!("Enter: return to overview (Esc + Enter: exit): ");
        io::stdout().flush().map_err(|e| e.to_string())?;
        let mut line = String::new();
        if io::stdin()
            .read_line(&mut line)
            .map_err(|e| e.to_string())?
            == 0
            || line.contains('\x1b')
        {
            return Ok(());
        }
    }
}

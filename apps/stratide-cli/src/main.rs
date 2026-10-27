use std::env;

fn main() {
    let command = env::args().nth(1).unwrap_or_else(|| "help".to_owned());
    match command.as_str() {
        "status" => println!("stratide {} — NOT RUNNING (M0 scaffold only)", stratide_contracts::VERSION),
        _ => println!("stratide-cli — M0 scaffold. Try: stratide-cli status"),
    }
}

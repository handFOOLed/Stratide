fn main() {
    let n=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap();
    println!("{}",n.as_nanos());
}

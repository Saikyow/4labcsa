fn print_str(s) {
    let i = 1;
    while (i <= s[0]) {
        out(1, s[i]);
        i = i + 1;
    }
}

fn main() {
    print_str("Hello, World!");
}

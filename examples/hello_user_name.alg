let buf[16];
let head = 0;
let tail = 0;
let name[32];

interrupt on_input() {
    buf[tail & 15] = in(0);
    tail = tail + 1;
}

fn read() {
    while (head == tail) {
    }
    let c = buf[head & 15];
    head = head + 1;
    return c;
}

fn print_str(s) {
    let i = 1;
    while (i <= s[0]) {
        out(1, s[i]);
        i = i + 1;
    }
}

fn main() {
    print_str("What is your name?\n");
    let c = read();
    while (c != '\n' && c != 0) {
        if (name[0] < 31) {
            name[0] = name[0] + 1;
            name[name[0]] = c;
        }
        c = read();
    }
    print_str("Hello, ");
    print_str(name);
    print_str("!");
}

// Эхо ввода до '\0'.

let buf[16];
let head = 0;
let tail = 0;

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

fn main() {
    let c = read();
    while (c != 0) {
        out(1, c);
        c = read();
    }
}

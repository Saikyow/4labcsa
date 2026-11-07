// y[i] = (x[i-1] + 2 * x[i] + x[i+1]) / 4, на краях берётся крайний отсчёт.
// Ввод: N (1..64), затем N отсчётов.

let buf[16];
let head = 0;
let tail = 0;
let x[64];
let y[64];

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

fn print_int(n) {
    let digits[10];
    if (n < 0) {
        out(1, '-');
    } else {
        n = -n;
    }
    // Работаем с n <= 0, иначе -2147483648 не напечатать.
    let count = 0;
    while (count == 0 || n != 0) {
        digits[count] = '0' - n % 10;
        n = n / 10;
        count = count + 1;
    }
    while (count > 0) {
        count = count - 1;
        out(1, digits[count]);
    }
}

fn filter(src, dst, n) {
    let i = 0;
    while (i < n) {
        let prev = src[i];
        let next = src[i];
        if (i > 0) {
            prev = src[i - 1];
        }
        if (i < n - 1) {
            next = src[i + 1];
        }
        dst[i] = (prev + 2 * src[i] + next) / 4;
        i = i + 1;
    }
}

fn main() {
    let n = read();
    if (n < 1 || n > 64) {
        print_int(-1);
        return;
    }
    let i = 0;
    while (i < n) {
        x[i] = read();
        i = i + 1;
    }
    filter(x, y, n);
    i = 0;
    while (i < n) {
        if (i > 0) {
            out(1, ' ');
        }
        print_int(y[i]);
        i = i + 1;
    }
}

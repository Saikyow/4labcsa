// main считает и печатает метки, обработчик эхом печатает ввод в верхнем регистре.

let done = 0;
let received = 0;

interrupt on_input() {
    let c = in(0);
    if (c == 0) {
        done = 1;
        return;
    }
    if (c >= 'a' && c <= 'z') {
        c = c - 'a' + 'A';
    }
    out(1, c);
    received = received + 1;
}

fn print_str(s) {
    let i = 1;
    while (i <= s[0]) {
        out(1, s[i]);
        i = i + 1;
    }
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

fn main() {
    let loops = 0;
    while (!done) {
        loops = loops + 1;
        if (loops % 10 == 0) {
            // Иначе эхо обработчика вклинится в середину метки.
            di();
            print_str("<main>");
            ei();
        }
    }
    print_str("\nreceived: ");
    print_int(received);
    print_str("\nmain loop iterations: ");
    print_int(loops);
}

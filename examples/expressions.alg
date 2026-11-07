// Приоритеты, деление с округлением к нулю, сдвиги, пул литералов, короткие && и ||.

let calls = 0;

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

fn show(n) {
    print_int(n);
    out(1, '\n');
}

fn touch() {
    calls = calls + 1;
    return 1;
}

fn main() {
    let a = 7;
    let b = -3;
    show(a + b * 2 - (a - b) / 3);
    show(a / b);
    show(a % b);
    show(-a % 3);
    show(1 << 31);
    show(-1 >> 28);
    show(0x12345678);
    show(2147483647 + 1);
    show((a & 5 | 8) ^ 1);
    show(~a);
    show(!a + !0);
    show(a > b == 1);
    show(b < 0 || touch());
    show(a < 0 && touch());
    show(a > 0 && touch());
    show(calls);
}

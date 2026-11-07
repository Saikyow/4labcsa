// Ввод: N, затем N чисел. Вывод: 1 простое, 0 составное, -1 если n < 1.

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

fn is_prime(n) {
    if (n < 1) {
        return -1;
    }
    if (n == 1) {
        return 0;
    }
    let i = 2;
    // Не `i * i <= n`: для n около 2^31 произведение переполнится.
    while (i <= n / i) {
        if (n % i == 0) {
            return 0;
        }
        i = i + 1;
    }
    return 1;
}

fn main() {
    let n = read();
    while (n > 0) {
        print_int(is_prime(read()));
        out(1, '\n');
        n = n - 1;
    }
}

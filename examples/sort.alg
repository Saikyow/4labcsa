// Ввод: N (0..32), затем N чисел. Иначе выводится -1.

let buf[16];
let head = 0;
let tail = 0;
let numbers[32];

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

fn sort(a, n) {
    let i = 1;
    while (i < n) {
        let x = a[i];
        let j = i - 1;
        while (j >= 0 && a[j] > x) {
            a[j + 1] = a[j];
            j = j - 1;
        }
        a[j + 1] = x;
        i = i + 1;
    }
}

fn main() {
    let n = read();
    if (n < 0 || n > 32) {
        print_int(-1);
        return;
    }
    let i = 0;
    while (i < n) {
        numbers[i] = read();
        i = i + 1;
    }
    sort(numbers, n);
    i = 0;
    while (i < n) {
        print_int(numbers[i]);
        out(1, '\n');
        i = i + 1;
    }
}

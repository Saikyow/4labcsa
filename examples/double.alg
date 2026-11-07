// 64-битные числа Фибоначчи F(k), k <= 93. Число хранится как [старшее, младшее] слово.
// Ввод: N, затем N номеров k.

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

fn print_str(s) {
    let i = 1;
    while (i <= s[0]) {
        out(1, s[i]);
        i = i + 1;
    }
}

fn copy64(dst, src) {
    dst[0] = src[0];
    dst[1] = src[1];
}

fn add64(dst, a, b) {
    let lo = a[1] + b[1];
    // Перенос: старший бит (a + b) / 2, эта сумма влезает в 32 бита.
    let carry = ((a[1] >> 1) + (b[1] >> 1) + (a[1] & b[1] & 1)) >> 31;
    dst[0] = a[0] + b[0] + carry;
    dst[1] = lo;
}

// x /= 10 столбиком по 16 бит, чтобы не выйти за int32.
fn div10(x) {
    let hi = x[0];
    let lo = x[1];
    let cur = hi >> 16;
    let q = cur / 10;
    cur = ((cur % 10) << 16) + (hi & 0xFFFF);
    x[0] = (q << 16) + cur / 10;
    cur = ((cur % 10) << 16) + (lo >> 16);
    q = cur / 10;
    cur = ((cur % 10) << 16) + (lo & 0xFFFF);
    x[1] = (q << 16) + cur / 10;
    return cur % 10;
}

fn print_u64(x) {
    let n[2];
    let digits[20];
    copy64(n, x);
    let count = 0;
    while (count == 0 || n[0] != 0 || n[1] != 0) {
        digits[count] = '0' + div10(n);
        count = count + 1;
    }
    while (count > 0) {
        count = count - 1;
        out(1, digits[count]);
    }
}

fn fib(dst, k) {
    let a[2];
    let b[2];
    let t[2];
    a[0] = 0;
    a[1] = 0;
    b[0] = 0;
    b[1] = 1;
    while (k > 0) {
        add64(t, a, b);
        copy64(a, b);
        copy64(b, t);
        k = k - 1;
    }
    copy64(dst, a);
}

fn main() {
    let result[2];
    let n = read();
    while (n > 0) {
        let k = read();
        if (k < 0 || k > 93) {
            print_str("-1");
        } else {
            fib(result, k);
            print_u64(result);
        }
        out(1, '\n');
        n = n - 1;
    }
}

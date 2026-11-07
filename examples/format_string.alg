// Ввод: строка формата (%d, %Nd, %-Nd), затем по строке на число. При ошибке выводится -1.
// Всё читается до вывода, чтобы при ошибке не было частичного результата.

let buf[16];
let head = 0;
let tail = 0;
let eof = 0;

let format[33];
let values[16];
let failed = 0;
let spec_left = 0;
let spec_width = 0;

interrupt on_input() {
    buf[tail & 15] = in(0);
    tail = tail + 1;
}

fn read() {
    if (eof) {
        return 0;
    }
    while (head == tail) {
    }
    let c = buf[head & 15];
    head = head + 1;
    if (c == 0) {
        eof = 1;
    }
    return c;
}

fn print_str(s) {
    let i = 1;
    while (i <= s[0]) {
        out(1, s[i]);
        i = i + 1;
    }
}

fn read_format() {
    let c = read();
    while (c != '\n' && c != 0) {
        if (format[0] == 0x20) {
            failed = 1;
        } else {
            format[0] = format[0] + 1;
            format[format[0]] = c;
        }
        c = read();
    }
}

// Число копится отрицательным, иначе -2147483648 не разобрать.
fn read_number() {
    let c = read();
    let negative = c == '-';
    if (c == '-' || c == '+') {
        c = read();
    }
    let value = 0;
    let count = 0;
    while (c != '\n' && c != 0) {
        let digit = c - '0';
        if (digit < 0 || digit > 9) {
            failed = 1;
        } else if (value < -214748364 || (value == -214748364 && digit > 8)) {
            failed = 1;
        } else {
            value = value * 10 - digit;
        }
        count = count + 1;
        c = read();
    }
    if (count == 0 || (!negative && value == -2147483648)) {
        failed = 1;
    }
    if (negative) {
        return value;
    }
    return -value;
}

fn parse_spec(i) {
    spec_left = i <= format[0] && format[i] == '-';
    i = i + spec_left;
    spec_width = 0;
    while (i <= format[0] && format[i] >= '0' && format[i] <= '9') {
        spec_width = spec_width * 10 + format[i] - '0';
        if (spec_width > 99) {
            return -1;
        }
        i = i + 1;
    }
    if (i > format[0] || format[i] != 'd') {
        return -1;
    }
    return i + 1;
}

fn print_padded(n, width, left) {
    let digits[11];
    let count = 0;
    let negative = n < 0;
    if (!negative) {
        n = -n;
    }
    while (count == 0 || n != 0) {
        digits[count] = '0' - n % 10;
        n = n / 10;
        count = count + 1;
    }
    let pad = width - count - negative;
    while (!left && pad > 0) {
        out(1, ' ');
        pad = pad - 1;
    }
    if (negative) {
        out(1, '-');
    }
    while (count > 0) {
        count = count - 1;
        out(1, digits[count]);
    }
    while (pad > 0) {
        out(1, ' ');
        pad = pad - 1;
    }
}

fn read_values() {
    let i = 1;
    let count = 0;
    while (i <= format[0] && !failed) {
        if (format[i] == '%') {
            i = parse_spec(i + 1);
            if (i < 0) {
                failed = 1;
            } else {
                values[count] = read_number();
                count = count + 1;
            }
        } else {
            i = i + 1;
        }
    }
}

fn print_formatted() {
    let i = 1;
    let count = 0;
    while (i <= format[0]) {
        if (format[i] == '%') {
            i = parse_spec(i + 1);
            print_padded(values[count], spec_width, spec_left);
            count = count + 1;
        } else {
            out(1, format[i]);
            i = i + 1;
        }
    }
}

fn main() {
    read_format();
    if (!failed) {
        read_values();
    }
    if (failed) {
        print_str("-1");
    } else {
        print_formatted();
    }
}

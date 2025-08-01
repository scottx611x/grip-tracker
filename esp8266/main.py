from machine import Pin, I2C, UART, reset
from time import ticks_us, ticks_diff, sleep_ms
from i2c_lcd import I2cLcd
from ssd1306 import SSD1306_I2C
from qrcode import display_qrcode
import uos


# Detaches the default REPL/print stream from the USB-serial port.
# After this call:
#   • The MicroPython REPL no longer appears over /dev/ttyUSB0.
#   • Ordinary print() output is discarded (unless a new stream is attached).
#   • The port is still usable as a raw UART if you explicitly create
#     a machine.UART(0, …) object and call uart.read()/write() (like we do below)
#
# In our case we're using this to prevent the REPL from corrupting the incoming stream of grip strength data
uos.dupterm(None, 1)


# ---------- I²C Bus ----------
# I have a low res LCD for grip data and a higher res OLED to render a QRCode
# both share the I2C bus
i2c = I2C(scl=Pin(5), sda=Pin(4))      # D1=SCL, D2=SDA

addr = i2c.scan()

lcd_addr  = 0x27 if 0x27 in addr else 0x3f
oled_addr = 0x3c if 0x3c in addr else 0x3d

lcd  = I2cLcd(i2c, lcd_addr, 2, 16)
oled = SSD1306_I2C(128, 64, i2c, addr=oled_addr)

display_qrcode(oled)

# ---------- UART ----------
# We're reading live grip strength data from the ADC display's TXD pin
uart = UART(0, baudrate=9600, rx=3, tx=1)


def lcd_update(current_grip, max_grip, _lcd: I2cLcd):
    _lcd.move_to(7, 0); _lcd.putstr("{:6.1f}".format(float(current_grip)))
    _lcd.move_to(7, 1); _lcd.putstr("{:6.1f}".format(float(max_grip)))


def main():
    buf = b''
    max_grip = 0.0
    lcd.clear()
    lcd.putstr(" Grip :\n Max  :")

    while True:
        if uart.any():
            buf += uart.read()
            sbuf = str(buf)

            sbuf = sbuf[:-5]
            _, value = sbuf.split("=")

            if float(value) >= max_grip:
                max_grip = float(value)

            lcd_update(value, max_grip, lcd)
            uart.write("{:.2f}@{:.2f}\n".format(float(value), max_grip))
            buf = b''

        sleep_ms(10)


try:
    main()
except Exception:
    lcd.clear()
    lcd.putstr("Error detected\nRebooting... <3")

    uos.dupterm(uart, 1)
    reset()


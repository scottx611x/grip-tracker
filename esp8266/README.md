### Setup

1. `pip install esptool mpremote`

### Erasing flash and flashing micropython

```
# Find usb device
$ ls /dev | grep tty

# Erase flash
$ esptool.py --port /dev/tty.SLAB_USBtoUART erase_flash


# Flash micropython
$ esptool.py --port /dev/tty.SLAB_USBtoUART \
    --baud 460800 \
    write_flash --flash-size=detect 0 \
    ./esp8266/ESP8266_GENERIC-20250415-v1.25.0.bin
```

### Copy Files

```
$ mpremote connect /dev/tty.SLAB_USBtoUART fs cp  ./*.py :
```
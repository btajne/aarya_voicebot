import serial
import time

PORT = "/dev/ttyACM0"
BAUD = 9600

ser = serial.Serial(PORT, BAUD, timeout=1)
time.sleep(2)

def send(msg):
    ser.write((msg + "\n").encode())
    print(">> Sent:", msg)

def receive():
    if ser.in_waiting:
        return ser.readline().decode().strip()

while True:
    msg = input("Type message (or exit): ")
    if msg.lower() == "exit":
        break

    send(msg)

    time.sleep(0.3)

    reply = receive()
    if reply:
        print("<< Arduino:", reply)

ser.close()

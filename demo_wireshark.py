import socket
import sys
from app.security.crypto import CryptoBox, load_key

HOST = "127.0.0.1"
PORT = 9000

def run_receiver():
    box = CryptoBox(load_key())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print(f"[*] Dang lang nghe UDP tai {HOST}:{PORT}...")
    while True:
        data, addr = sock.recvfrom(4096)
        print(f"\n[+] Nhan duoc {len(data)} bytes ma hoa (Hex): {data.hex()}")
        try:
            plaintext = box.decrypt(data, aad=b"DEMO_HEADER").decode("utf-8")
            print(f"[+] Giai ma thanh cong: {plaintext}")
        except Exception as e:
            print(f"[-] Loi giai ma: {e}")

def run_sender():
    box = CryptoBox(load_key())
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = b"HELLO_TEACHER_123"
    encrypted = box.encrypt(msg, aad=b"DEMO_HEADER")
    sock.sendto(encrypted, (HOST, PORT))
    print(f"[*] Da gui '{msg.decode()}' -> {len(encrypted)} bytes ma hoa toi {HOST}:{PORT}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        run_sender()
    else:
        run_receiver()
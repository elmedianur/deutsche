"""
Deploy changes to server via SSH
Dinamik tugmalar va is_admin_async funksiyalarini serverga yuklash
"""
import paramiko
import os
import sys

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Server credentials
HOST = "89.39.94.132"
USERNAME = "root"
PASSWORD = "11_Nurali_11"

# Files to upload
FILES_TO_UPLOAD = [
    ("deploy/src/keyboards/inline.py", "/app/src/keyboards/inline.py"),
    ("deploy/src/services/button_service.py", "/app/src/services/button_service.py"),
    ("deploy/src/handlers/admin/panel.py", "/app/src/handlers/admin/panel.py"),
    ("deploy/src/handlers/user/start.py", "/app/src/handlers/user/start.py"),
    ("deploy/src/handlers/user/menu.py", "/app/src/handlers/user/menu.py"),
    ("deploy/src/handlers/quiz/simple.py", "/app/src/handlers/quiz/simple.py"),
    ("deploy/src/handlers/quiz/personal.py", "/app/src/handlers/quiz/personal.py"),
    ("deploy/src/handlers/payment/stars.py", "/app/src/handlers/payment/stars.py"),
    # Kritik muammolar tuzatilgan fayllar
    ("deploy/src/bot.py", "/app/src/bot.py"),
    ("deploy/src/core/redis.py", "/app/src/core/redis.py"),
    ("deploy/src/middlewares/auth.py", "/app/src/middlewares/auth.py"),
    ("deploy/src/config/settings.py", "/app/src/config/settings.py"),
    ("deploy/src/services/payment_service.py", "/app/src/services/payment_service.py"),
    # Tournament va achievement xatolar tuzatilgan
    ("deploy/src/services/tournament_service.py", "/app/src/services/tournament_service.py"),
    ("deploy/src/services/__init__.py", "/app/src/services/__init__.py"),
    # Ichki menyu tugmalari dinamik qilingan
    ("deploy/src/handlers/shop/__init__.py", "/app/src/handlers/shop/__init__.py"),
    ("deploy/src/handlers/tournament/__init__.py", "/app/src/handlers/tournament/__init__.py"),
    # User model (stars field qo'shildi)
    ("deploy/src/database/models/user.py", "/app/src/database/models/user.py"),
    # Kritik xatolar tuzatildi
    ("deploy/src/core/redis.py", "/app/src/core/redis.py"),
    ("deploy/src/core/security.py", "/app/src/core/security.py"),
    ("deploy/src/middlewares/auth.py", "/app/src/middlewares/auth.py"),
]

def main():
    print("[*] Serverga ulanmoqda...")

    # Create SSH client
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(HOST, username=USERNAME, password=PASSWORD)
        print("[+] Server bilan bog'landi!")

        # Create SFTP client
        sftp = client.open_sftp()

        # Get local path
        local_base = os.path.dirname(os.path.abspath(__file__))

        # Upload files
        for local_rel, remote_path in FILES_TO_UPLOAD:
            local_path = os.path.join(local_base, local_rel)

            if os.path.exists(local_path):
                print(f"[>] Yuklanmoqda: {local_rel} -> {remote_path}")

                # Make sure remote directory exists
                remote_dir = os.path.dirname(remote_path)
                try:
                    sftp.stat(remote_dir)
                except FileNotFoundError:
                    # Create directory
                    stdin, stdout, stderr = client.exec_command(f"mkdir -p {remote_dir}")
                    stdout.read()

                # Upload file
                sftp.put(local_path, remote_path)
                print(f"    [+] Yuklandi!")
            else:
                print(f"    [!] Fayl topilmadi: {local_path}")

        sftp.close()

        # Restart bot
        print("\n[*] Bot qayta ishga tushirilmoqda...")
        # Try different docker restart methods
        stdin, stdout, stderr = client.exec_command("docker restart quiz_bot_pro 2>/dev/null || docker-compose -f /app/docker-compose.yml restart quiz_bot_pro 2>/dev/null || cd /root && docker compose restart quiz_bot_pro")
        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            print("[+] Bot muvaffaqiyatli qayta ishga tushdi!")
        else:
            print(f"[!] Qayta ishga tushirishda xatolik: {stderr.read().decode()}")

        # Wait for bot to start
        import time
        print("\n[*] Bot ishga tushishini kutmoqda (5 soniya)...")
        time.sleep(5)

        # Check bot logs
        print("\n[*] Bot loglari (oxirgi 15 qator):")
        stdin, stdout, stderr = client.exec_command("docker logs quiz_bot_pro --tail 15 2>&1")
        print(stdout.read().decode())

        client.close()
        print("\n[+] Deploy yakunlandi!")

    except Exception as e:
        print(f"[-] Xatolik: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

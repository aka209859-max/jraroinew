"""初期セットアップスクリプト"""
import subprocess
import sys

def main():
    print("Enable Edge Engine - Setup")
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    print("Setup complete.")

if __name__ == "__main__":
    main()

import os
import sys
from playwright.sync_api import sync_playwright

SESSION_DIR = os.path.abspath("browser_session")
os.makedirs(SESSION_DIR, exist_ok=True)

print("🚀 Запуск Google Chrome для авторизации...")
with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(
        user_data_dir=SESSION_DIR,
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled"]
    )
    page = browser.new_page()
    page.goto("https://www.instagram.com/accounts/login/")
    
    print("\n👉 В открывшемся окне Chrome войдите в Instagram.")
    print("👉 Когда откроется лента профиля, вернитесь в терминал и нажмите ENTER...")
    input()
    
    browser.close()
    print("✅ Сессия успешно сохранена!")

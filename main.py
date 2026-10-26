import json
import os
import time
from collections import defaultdict, deque
 
import aiohttp
import discord
from dotenv import load_dotenv
 
load_dotenv()
 
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL", "api")#your api keys (local ai or else)
MODEL = os.getenv("MODEL", "gemma3:4b")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", "You are a helpful assistant.")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "10"))
REPLY_ALWAYS_CHANNEL_ID = os.getenv("REPLY_ALWAYS_CHANNEL_ID")
 
if not DISCORD_TOKEN:
    raise SystemExit("DISCORD_TOKEN not found in the .env file")
 
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
 
history = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
 
 
async def stream_ollama(channel_id: int, prompt: str):
    """Send a prompt to Ollama and return the accumulated text in parts."""
    history[channel_id].append({"role": "user", "content": prompt})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history[channel_id]]
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": "30m",
    }
 
    full = ""
    timeout = aiohttp.ClientTimeout(total=600, sock_read=300)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(OLLAMA_URL, json=payload) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Ollama {resp.status}: {await resp.text()}")
                async for line in resp.content:
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        full += chunk
                        yield full
                    if data.get("done"):    
                        break
    except Exception:
        history[channel_id].pop()
        raise
 
    if full:
        history[channel_id].append({"role": "assistant", "content": full})
 
 
def should_reply(message: discord.Message) -> bool:
    if message.author.bot:
        return False
    return True
 
 
@client.event
async def on_ready():
    print(f"ล็อกอินแล้วในชื่อ {client.user} (model: {MODEL})")
 
 
@client.event
async def on_message(message: discord.Message):
    if not should_reply(message):
        return
 
    prompt = (
        message.content.replace(f"<@{client.user.id}>", "")
        .replace(f"<@!{client.user.id}>", "")
        .strip()
    )
    if not prompt:
        return
 
    if prompt.lower() in ("!reset", "!clear"):
        history[message.channel.id].clear()
        await message.reply("Clear history chat")
        return
 
    sent = await message.reply("Thinking...")
    start = time.time()
    last_edit = 0.0
    first = True
    text = ""
 
    try:
        async for text in stream_ollama(message.channel.id, prompt):
            if first:
                print(f"Got first word in {time.time() - start:.1f} seconds")
                first = False
            if time.time() - last_edit > 1.5:
                await sent.edit(content=text[:1900])
                last_edit = time.time()
    except Exception as e:
        print(f"error: {e!r}")
        await sent.edit(content="Unable to connect to AI, or AI is not responding")
        return
 
    print(f"Completed in {time.time() - start:.1f} seconds")
 
    if not text:
        await sent.edit(content="AI did not return a response")
        return
 
    await sent.edit(content=text[:1900])
    for i in range(1900, len(text), 1900):
        await message.channel.send(text[i : i + 1900])
 
 
client.run(DISCORD_TOKEN)

#made by https://github.com/Pimanut
 
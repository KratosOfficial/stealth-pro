import asyncio
import discord
import random
import threading
import base64
from nicegui import ui
from datetime import datetime
from io import BytesIO

# --- SYSTEM STATE & THREAD COMMUNICATION ---
class BotState:
    def __init__(self):
        self.is_running = False
        self.ui_status = "OFFLINE"
        self.last_ui_status = ""
        
        self.logs = []  
        self.last_log_count = 0
        
        self.token = ""
        self.target_list = []  
        self.message = ""
        self.source_chan = ""
        self.msg_id = ""
        self.op_mode = 'MANUAL CONTENT'
        self.auto_mode = 'loop'
        self.loop_mins = 30
        self.sched_time = "21:00"
        self.images = []  
        self.client = None

state = BotState()

# --- SAFE LOGGING WITH BULLETPROOF INLINE CSS ---
def add_log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    upper_msg = msg.upper()
    
    msg_color = "#e4e4e7" 
    if "ERROR" in upper_msg or "CRITICAL" in upper_msg:
        msg_color = "#f43f5e"  
    elif "SUCCESS" in upper_msg or "ONLINE" in upper_msg:
        msg_color = "#10b981"  
    elif "TRYING" in upper_msg or "WAITING" in upper_msg or "NETWORK" in upper_msg or "INIT" in upper_msg:
        msg_color = "#f59e0b"  
    elif "STOPPING" in upper_msg:
        msg_color = "#fb7185"  

    formatted_msg = f'<div style="margin-bottom: 4px; font-size: 0.8rem; font-family: monospace;"><span style="color: #71717a; font-weight: 500;">[{timestamp}]</span> <span style="color: {msg_color}; font-weight: bold;">{msg}</span></div>'
    state.logs.append(formatted_msg)
    
    ansi_prefix = "\033[97m" 
    if "ERROR" in upper_msg or "CRITICAL" in upper_msg:
        ansi_prefix = "\033[91m" 
    elif "SUCCESS" in upper_msg or "ONLINE" in upper_msg:
        ansi_prefix = "\033[92m" 
    elif "TRYING" in upper_msg or "WAITING" in upper_msg or "NETWORK" in upper_msg or "INIT" in upper_msg:
        ansi_prefix = "\033[93m" 
    elif "STOPPING" in upper_msg:
        ansi_prefix = "\033[95m" 

    ansi_reset = "\033[0m"
    print(f"{ansi_prefix}[{timestamp}] {msg}{ansi_reset}")

# --- BACKGROUND DISCORD ENGINE ---
async def automation_loop(client):
    last_run_time = ""
    while state.is_running:
        now = datetime.now()
        should_dispatch = False

        if state.auto_mode == 'loop':
            should_dispatch = True
        elif state.auto_mode == 'schedule':
            current_str = now.strftime("%H:%M")
            if current_str == state.sched_time and last_run_time != current_str:
                should_dispatch = True
                last_run_time = current_str

        if should_dispatch:
            target_ids = [int(i) for i in state.target_list]
            add_log(f"TRYING: Targeting {len(target_ids)} channels...") 
            
            for c_id in target_ids:
                if not state.is_running: break
                chan = client.get_channel(c_id)
                if chan:
                    try:
                        if state.op_mode == 'FORWARD MESSAGE':
                            src_chan = await client.fetch_channel(int(state.source_chan))
                            msg = await src_chan.fetch_message(int(state.msg_id))
                            await msg.forward(chan)
                            add_log(f"SUCCESS: Forwarded to ID {c_id}") 
                        else:
                            has_media = len(state.images) > 0
                            text_content = state.message.strip() if state.message else None
                            
                            if not text_content and not has_media:
                                add_log(f"WARNING: Skipped ID {c_id} - No payload (text or media) provided.")
                                continue
                                
                            files_to_send = [discord.File(BytesIO(img['data']), filename=img['name']) for img in state.images]
                            
                            await chan.send(content=text_content, files=files_to_send)
                            add_log(f"SUCCESS: Sent to ID {c_id}") 
                    except Exception as e:
                        add_log(f"ERROR: Failed on ID {c_id} ({e})") 
                else:
                    add_log(f"ERROR: Could not access channel {c_id}. Check permissions.") 
                await asyncio.sleep(random.uniform(2, 4))
            
            if state.auto_mode == 'loop':
                wait_sec = int(state.loop_mins) * 60 + random.randint(0, 60)
                add_log(f"WAITING: Sleeping... Next loop in {state.loop_mins}m") 
                for _ in range(wait_sec):
                    if not state.is_running: break
                    await asyncio.sleep(1)
            else:
                await asyncio.sleep(60)
        else:
            await asyncio.sleep(1)

def run_discord_thread():
    asyncio.set_event_loop(asyncio.new_event_loop())
    if not state.token or not state.target_list:
        add_log("ERROR: Token or Target IDs missing! Setup config first.")
        state.ui_status = "OFFLINE"
        state.is_running = False
        return

    clean_token = state.token.strip().strip('"').strip("'")
    
    try:
        client = discord.Client()
        state.client = client
    except Exception as e:
        add_log(f"CRITICAL: Engine initialization failed - {e}")
        state.ui_status = "OFFLINE"
        state.is_running = False
        return

    @client.event
    async def on_ready():
        add_log(f"SUCCESS: Authenticated to Discord as {client.user}")
        state.ui_status = "ONLINE"
        client.loop.create_task(automation_loop(client))

    try:
        add_log("NETWORK: Authenticating with Discord servers...")
        client.run(clean_token)
    except discord.LoginFailure:
        add_log("ERROR: Invalid Token! Check if you installed discord.py-self.")
        state.ui_status = "OFFLINE"
        state.is_running = False
    except Exception as e:
        add_log(f"ERROR: Disconnected - {e}")
        state.ui_status = "OFFLINE"
        state.is_running = False

# --- UI ACTIONS ---
def handle_start():
    if state.is_running: return
    
    validation_failed = False
    if not state.token:
        token_input.props(remove='hint').props('error error-message="Required field!"')
        validation_failed = True
    if not state.target_list:
        target_input.props(remove='hint').props('error error-message="At least one Target ID is required!"')
        validation_failed = True
        
    if validation_failed:
        ui.notify("Engine aborted. Please fill out the required fields.", type='negative')
        return

    state.is_running = True
    state.ui_status = "INIT"
    add_log("INIT: Engine engaged by user. Spawning background thread...")
    threading.Thread(target=run_discord_thread, daemon=True).start()

def handle_stop():
    if not state.is_running: return
    state.ui_status = "OFFLINE"
    add_log("STOPPING: System manually halted.")
    state.is_running = False
    if state.client and state.client.loop:
        asyncio.run_coroutine_threadsafe(state.client.close(), state.client.loop)

# --- SMART CHIP & VALIDATION LOGIC ---
def add_token(e):
    val = token_input.value.strip()
    if val:
        if state.token:
            ui.notify("Only one token allowed! Remove the existing one first.", type='warning')
        else:
            state.token = val
            token_input.set_value('')
            refresh_token_chip()

def remove_token():
    state.token = ""
    refresh_token_chip()

def refresh_token_chip():
    token_chip_container.clear()
    if state.token:
        token_chip_container.set_visibility(True)
        token_input.props(remove='error error-message').props('hint="Press Enter to save"')
        with token_chip_container:
            display_str = f"{state.token[:5]}...{state.token[-5:]}" if len(state.token) > 10 else "********"
            with ui.badge(outline=True).classes('px-2 py-0.5 text-xs bg-emerald-500/10 border border-emerald-500/50 text-emerald-400 rounded-full gap-1.5 items-center shadow-[0_0_8px_rgba(16,185,129,0.15)]'):
                ui.label(display_str).classes('font-mono')
                ui.icon('close').classes('cursor-pointer hover:text-white transition-colors').on('click', remove_token)
    else:
        token_chip_container.set_visibility(False)
        token_input.props(remove='error error-message').props('hint="Press Enter to save"')

def add_target(e):
    val = target_input.value.strip()
    if val and val.isdigit() and val not in state.target_list:
        state.target_list.append(val)
        target_input.set_value('')
        refresh_chips()

def remove_target(val):
    state.target_list.remove(val)
    refresh_chips()

def refresh_chips():
    chip_container.clear()
    if state.target_list:
        chip_container.set_visibility(True)
        target_input.props(remove='error error-message').props('hint="Press Enter to save"')
        with chip_container:
            for t in state.target_list:
                with ui.badge(outline=True).classes('px-2 py-0.5 text-xs bg-cyan-500/10 border border-cyan-500/50 text-cyan-400 rounded-full gap-1.5 items-center shadow-[0_0_8px_rgba(6,182,212,0.15)]'):
                    ui.label(t).classes('font-mono')
                    ui.icon('close').classes('cursor-pointer hover:text-white transition-colors').on('click', lambda _, x=t: remove_target(x))
    else:
        chip_container.set_visibility(False)
        target_input.props(remove='error error-message').props('hint="Press Enter to save"')

# --- MEDIA LOGIC (UPDATED FOR NICEGUI V3+) ---
async def handle_upload(e):
    try:
        if len(state.images) >= 10:
            ui.notify("Maximum 10 images reached", type='warning')
            return
        
        # New syntax for NiceGUI: access .file object and await the read()
        file_data = await e.file.read()
        file_name = e.file.name
        
        if not file_data:
            add_log(f"ERROR: Upload failed - file '{file_name}' is totally empty.")
            return
            
        state.images.append({'name': file_name, 'data': file_data})
        add_log(f"SUCCESS: Attached media '{file_name}' to payload.") 
        update_image_ui()
        
        if 'media_uploader' in globals():
            media_uploader.reset() 

    except Exception as ex:
        add_log(f"ERROR: Media processing crashed - {ex}")

def update_image_ui():
    count = len(state.images)
    img_counter.set_text(f"{count}/10 Files Attached")
    img_counter.style(f"color: {'#22d3ee' if count > 0 else '#71717a'}")
    img_preview_box.set_visibility(count > 0)
    file_list_display.clear()
    
    with file_list_display:
        for idx, img in enumerate(state.images):
            ext = img['name'].split('.')[-1].lower() if '.' in img['name'] else ''
            mime = f"image/{ext}" if ext in ['png', 'jpg', 'jpeg', 'gif', 'webp'] else "application/octet-stream"
            b64 = base64.b64encode(img['data']).decode('utf-8')
            src = f"data:{mime};base64,{b64}"
            
            with ui.row().classes('items-center justify-between bg-black/40 p-2 rounded-lg border border-white/5 mb-1 w-full'):
                with ui.row().classes('items-center gap-3 no-wrap'):
                    ui.image(src).classes('w-10 h-10 rounded object-cover border border-white/10')
                    ui.label(img['name']).classes('text-[11px] text-zinc-300 truncate w-40 font-mono')
                ui.button(icon='delete', on_click=lambda _, i=idx: delete_single_image(i)).props('flat round dense').classes('text-rose-400 hover:bg-rose-500/20')

def delete_single_image(index):
    state.images.pop(index)
    update_image_ui()
    add_log("CLEARED: Removed single media item from payload.")

def clear_all_manual():
    state.message = ""
    state.images = []
    msg_textarea.set_value('')
    if 'media_uploader' in globals():
        media_uploader.reset() 
    update_image_ui()
    add_log("CLEARED: Entire manual content payload wiped.")

def open_help():
    with ui.dialog() as dialog, ui.card().classes('bg-zinc-900 border border-cyan-500/30 p-8 max-w-md rounded-3xl shadow-[0_0_40px_rgba(6,182,212,0.15)]'):
        ui.label('Configuration Guide').classes('text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500 mb-6')
        ui.label('🔑 USER TOKEN').classes('text-xs font-bold text-zinc-400 tracking-widest mb-1')
        ui.label('Browser > F12 > Network > Filter "messages" > Find "authorization" in headers.').classes('text-sm text-zinc-300 mb-6 bg-black/30 p-3 rounded-xl border border-white/5')
        ui.label('🎯 CHANNEL IDs').classes('text-xs font-bold text-zinc-400 tracking-widest mb-1')
        ui.label('Right click channel > Copy ID. Enable Developer Mode in Settings first.').classes('text-sm text-zinc-300 bg-black/30 p-3 rounded-xl border border-white/5')
        ui.button('ACKNOWLEDGE', on_click=dialog.close).classes('w-full mt-8 bg-cyan-600 text-white font-bold rounded-xl shadow-[0_0_15px_rgba(8,145,178,0.4)]')
    dialog.open()


# --- MODERN UI STYLING & CUSTOM CSS ---
ui.add_head_html('''
<style>
    body {
        background: radial-gradient(circle at top right, #12121a, #09090b);
        color: #e4e4e7;
        font-family: "Inter", "Segoe UI", sans-serif;
    }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #27272a; border-radius: 10px; }
    ::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
    
    .btn-engine { transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important; border: none !important; }
    .btn-stop:hover { box-shadow: 0 0 20px rgba(244,63,94,0.3) !important; background-color: rgba(244,63,94,0.1) !important; }
    .clean-uploader .q-uploader__list { display: none !important; }
    .clean-uploader { height: auto !important; min-height: 0 !important; }
</style>
''')

# --- UI LAYOUT ---
with ui.header().classes('bg-[#09090b]/60 backdrop-blur-xl border-b border-white/5 items-center px-8 z-50 shadow-sm').style('height: 75px'):
    ui.label('⬡').classes('text-3xl text-cyan-500 drop-shadow-[0_0_10px_rgba(6,182,212,0.6)]')
    ui.label('STEALTH').classes('ml-2 text-xl font-black text-white tracking-widest')
    ui.label('PRO').classes('ml-1 text-xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-500 tracking-widest')
    
    header_clock = ui.label('00:00:00').classes('ml-10 text-xl font-mono font-black text-cyan-400 bg-black/40 px-5 py-2 rounded-xl border border-cyan-500/30 shadow-[0_0_15px_rgba(6,182,212,0.2)]')
    
    ui.space()
    status_light = ui.label('● SYSTEM OFFLINE').classes('text-xs font-bold tracking-[0.2em] text-zinc-500 transition-colors duration-300')

with ui.row().classes('w-full no-wrap h-screen mt-[-75px] pt-[75px]'):
    
    with ui.column().classes('w-80 bg-white/[0.02] backdrop-blur-md p-6 border-r border-white/5 h-full relative'):
        with ui.row().classes('w-full justify-between items-center mb-6'):
            ui.label('CONFIGURATION').classes('text-zinc-500 text-[10px] font-bold tracking-widest')
            ui.button(icon='help_outline', on_click=open_help).props('flat round dense color=cyan-500').classes('opacity-70 hover:opacity-100')

        with ui.column().classes('w-full mb-4 gap-0'):
            token_input = ui.input('User Token', password=True).classes('w-full').props('standout dense stack-label dark color=cyan rounded-xl hint="Press Enter to save"')
            token_input.on('keydown.enter', add_token)
            token_chip_container = ui.row().classes('w-full gap-2 mt-2 flex-wrap')
            token_chip_container.set_visibility(False)
        
        with ui.column().classes('w-full mb-6 gap-0'):
            target_input = ui.input('Target IDs').classes('w-full').props('standout dense stack-label dark color=cyan rounded-xl hint="Press Enter to save"')
            target_input.on('keydown.enter', add_target)
            chip_container = ui.row().classes('w-full gap-2 mt-2 flex-wrap')
            chip_container.set_visibility(False)
        
        ui.separator().classes('bg-white/5 mb-6 w-full')
        
        start_btn = ui.button('START ENGINE', on_click=handle_start).classes('w-full py-5 font-black tracking-widest rounded-2xl mb-4 btn-engine text-sm')
        start_btn.style('background: linear-gradient(135deg, #0891b2, #0284c7) !important; box-shadow: 0 0 20px rgba(8,145,178,0.3) !important; color: white !important;')
        
        ui.button('EMERGENCY STOP', on_click=handle_stop).classes('w-full py-4 font-bold tracking-widest rounded-2xl text-rose-500 border border-rose-500/50 btn-stop text-xs').props('outline')

    with ui.column().classes('flex-grow p-10 items-center overflow-y-auto'):
        
        with ui.card().classes('w-full max-w-4xl bg-[#121214]/80 backdrop-blur-xl border border-white/5 p-0 rounded-[2rem] overflow-hidden shadow-[0_20px_50px_rgba(0,0,0,0.5)]'):
            with ui.tabs().classes('w-full bg-black/40 text-zinc-400 h-16') as tabs:
                t1 = ui.tab('MANUAL CONTENT', icon='edit_square').classes('font-bold tracking-wider text-xs')
                t2 = ui.tab('FORWARD MESSAGE', icon='shortcut').classes('font-bold tracking-wider text-xs')
            
            with ui.tab_panels(tabs, value=t1).classes('w-full bg-transparent p-10').bind_value(state, 'op_mode'):
                with ui.tab_panel(t1):
                    msg_textarea = ui.textarea('Message Content').classes('w-full mb-6').bind_value(state, 'message').props('outlined dark color=cyan rounded-2xl')
                    
                    with ui.row().classes('w-full items-center justify-between bg-black/20 p-4 rounded-2xl border border-white/5'):
                        with ui.row().classes('items-center gap-6'):
                            global media_uploader
                            media_uploader = ui.upload(on_upload=handle_upload, label="Attach Media", auto_upload=True).classes('max-w-xs clean-uploader').props('flat color=cyan dense multiple')
                            img_counter = ui.label("0/10 Files Attached").classes('text-[10px] font-bold text-zinc-500 uppercase tracking-widest')
                        
                        ui.button('CLEAR ALL', on_click=clear_all_manual).props('flat dense').classes('text-xs font-bold text-rose-400 hover:bg-rose-500/10 px-4 py-2 rounded-xl')

                    with ui.column().classes('w-full mt-4 p-5 bg-black/30 rounded-2xl border border-white/5') as img_preview_box:
                        ui.label('MEDIA PAYLOAD').classes('text-[10px] font-bold text-cyan-500 tracking-widest mb-3')
                        file_list_display = ui.column().classes('w-full gap-2')
                    img_preview_box.set_visibility(False)

                with ui.tab_panel(t2):
                    ui.input('Source Channel ID').classes('w-full mb-6').bind_value(state, 'source_chan').props('outlined dark color=cyan rounded-xl')
                    ui.input('Source Message ID').classes('w-full').bind_value(state, 'msg_id').props('outlined dark color=cyan rounded-xl')

        with ui.card().classes('w-full max-w-4xl mt-8 bg-[#121214]/80 backdrop-blur-xl border border-white/5 p-4 rounded-[2rem] shadow-[0_20px_50px_rgba(0,0,0,0.5)]'):
            ui.label('AUTOMATION DIRECTIVES').classes('text-[10px] font-bold text-zinc-500 mb-4 text-center tracking-[0.2em] w-full')
            with ui.row().classes('w-full justify-center items-center gap-6'):
                ui.radio({'loop': 'Loop Interval', 'schedule': 'Daily Schedule'}, value='loop').bind_value(state, 'auto_mode').props('inline dark color=cyan')
                
                with ui.row().classes('items-center bg-black/30 px-4 py-1 rounded-xl border border-white/5').bind_visibility_from(state, 'auto_mode', backward=lambda v: v == 'loop'):
                    ui.number(value=30).classes('w-16').bind_value(state, 'loop_mins').props('dark borderless dense')
                    ui.label('minutes').classes('text-zinc-500 font-bold text-[10px] tracking-widest ml-1')
                
                with ui.row().classes('items-center bg-black/30 px-3 py-1 rounded-xl border border-white/5').bind_visibility_from(state, 'auto_mode', backward=lambda v: v == 'schedule'):
                    with ui.input().bind_value(state, 'sched_time').props('dark borderless dense').classes('w-28') as time_input:
                        with time_input.add_slot('append'):
                            ui.icon('schedule').classes('cursor-pointer text-cyan-500 text-sm').on('click', lambda: time_menu.open())
                        with ui.menu().props('dark') as time_menu:
                            ui.time().bind_value(state, 'sched_time').props('format24h dark color=cyan')

        ui.label('LIVE TELEMETRY FEED').classes('mt-10 text-[10px] font-bold text-zinc-600 tracking-[0.2em] w-full max-w-4xl mb-3 pl-2')
        with ui.scroll_area().classes('w-full max-w-4xl bg-black/80 backdrop-blur-2xl border border-white/10 rounded-[2rem] p-8 shadow-inner shadow-black/50').style('height: 280px;') as log_scroll:
            log_html = ui.html('')

def update_ui_elements():
    header_clock.set_text(datetime.now().strftime("%H:%M:%S"))

    if len(state.logs) > state.last_log_count:
        full_html = "".join(state.logs)
        log_html.set_content(full_html)
        try:
            log_scroll.scroll_to(percent=1.0)
        except:
            ui.run_javascript(f'const el = document.getElementById("c{log_scroll.id}"); if(el) el.scrollTop = el.scrollHeight;')
        state.last_log_count = len(state.logs)

    if state.ui_status != state.last_ui_status:
        if state.ui_status == "OFFLINE":
            status_light.style('color: #71717a; text-shadow: none;').set_text('● SYSTEM OFFLINE')
            start_btn.set_text('START ENGINE')
            start_btn.style('background: linear-gradient(135deg, #0891b2, #0284c7) !important; box-shadow: 0 0 20px rgba(8,145,178,0.3) !important; color: white !important;')
            
        elif state.ui_status == "INIT":
            status_light.style('color: #eab308; text-shadow: 0 0 10px rgba(234,179,8,0.8);').set_text('● INITIALIZING...')
            start_btn.set_text('INITIALIZING...')
            start_btn.style('background: linear-gradient(135deg, #eab308, #d97706) !important; box-shadow: 0 0 30px rgba(234,179,8,0.6) !important; color: black !important;')
            
        elif state.ui_status == "ONLINE":
            status_light.style('color: #10b981; text-shadow: 0 0 10px rgba(16,185,129,0.8);').set_text('● SYSTEM ONLINE')
            start_btn.set_text('ENGINE ACTIVE')
            start_btn.style('background: linear-gradient(135deg, #10b981, #059669) !important; box-shadow: 0 0 30px rgba(16,185,129,0.6) !important; color: black !important;')
            
        state.last_ui_status = state.ui_status

ui.timer(0.5, update_ui_elements)

ui.run(
    title='Stealth Pro Cloud',
    port=int(os.environ.get("PORT", 8080)),
    dark=True
)
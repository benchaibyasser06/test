import os
import sqlite3
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from pypdf import PdfReader
import streamlit as st

# 1. Page Configuration
st.set_page_config(
    page_title="PEKKA AI Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. SQLite Database Setup for Session Persistence
DB_FILE = "pekka_database.db"

def init_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_type TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def load_messages_from_db(agent_type):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM messages WHERE agent_type = ?", (agent_type,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": row[0], "content": row[1]} for row in rows]

def save_message_to_db(agent_type, role, content):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (agent_type, role, content) VALUES (?, ?, ?)", (agent_type, role, content))
    conn.commit()
    conn.close()

def clear_messages_in_db(agent_type=None):
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    cursor = conn.cursor()
    if agent_type:
        cursor.execute("DELETE FROM messages WHERE agent_type = ?", (agent_type,))
    else:
        cursor.execute("DELETE FROM messages")
    conn.commit()
    conn.close()

# 3. Executive Dark Styling & Custom CSS
professional_css = """
<style>
    /* Global Page Styling */
    .stApp {
        background: #0B0F19;
        color: #F3F4F6;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
    
    /* Sidebar Slide Styling */
    [data-testid="stSidebar"] {
        background-color: #111827 !important;
        border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
    }
    
    /* PEKKA Brand Header Title */
    .app-title {
        font-size: 2.8rem !important;
        font-weight: 900;
        letter-spacing: 0.05em;
        background: linear-gradient(135deg, #F59E0B 0%, #10B981 35%, #0EA5E9 70%, #EC4899 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0px;
        filter: drop-shadow(0px 4px 15px rgba(245, 158, 11, 0.2));
    }
    .app-subtitle {
        color: #9CA3AF;
        font-size: 0.95rem;
        font-weight: 500;
    }

    /* Bot Header Banners */
    .chef-card-header {
        background: linear-gradient(90deg, rgba(245, 158, 11, 0.15) 0%, rgba(16, 185, 129, 0.15) 100%);
        border: 1px solid rgba(245, 158, 11, 0.3);
        border-radius: 14px;
        padding: 14px 18px;
        color: #FBBF24;
        font-weight: 700;
        font-size: 1.25rem;
        margin-bottom: 12px;
    }
    .sensai-card-header {
        background: linear-gradient(90deg, rgba(14, 165, 233, 0.15) 0%, rgba(99, 102, 241, 0.15) 100%);
        border: 1px solid rgba(14, 165, 233, 0.35);
        border-radius: 14px;
        padding: 14px 18px;
        color: #38BDF8;
        font-weight: 700;
        font-size: 1.25rem;
        margin-bottom: 12px;
    }
    .pocoloco-card-header {
        background: rgba(236, 72, 153, 0.12);
        border: 1px solid rgba(236, 72, 153, 0.3);
        border-radius: 14px;
        padding: 14px 18px;
        color: #F472B6;
        font-weight: 700;
        font-size: 1.25rem;
        margin-bottom: 12px;
    }

    /* Button Styling */
    .stButton>button, .stDownloadButton>button, [data-testid="stPopover"]>button {
        background: #1F2937 !important;
        color: #F3F4F6 !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 10px !important;
        padding: 8px 16px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease-in-out !important;
        width: 100%;
    }
    .stButton>button:hover, .stDownloadButton>button:hover, [data-testid="stPopover"]>button:hover {
        background: #374151 !important;
        border-color: rgba(255, 255, 255, 0.3) !important;
        transform: translateY(-1px);
    }

    /* Chat Messages */
    [data-testid="stChatMessage"] {
        background-color: rgba(17, 24, 39, 0.7) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
        margin-bottom: 10px !important;
    }
</style>
"""
st.markdown(professional_css, unsafe_allow_html=True)

# 4. Load API Keys
load_dotenv(override=True)
raw_keys = os.getenv("GEMINI_API_KEYS") or os.getenv("GEMINI_API_KEY")

if not raw_keys:
    st.error("Configuration Error: No GEMINI_API_KEYS found in your .env file.")
    st.stop()

api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

if "key_index" not in st.session_state:
    st.session_state.key_index = 0

if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""

if "selected_language" not in st.session_state:
    st.session_state.selected_language = "Algerian Darja (الدارجة الجزائرية)"

if "sensai_quiz_mode" not in st.session_state:
    st.session_state.sensai_quiz_mode = False

if "anki_cards_csv" not in st.session_state:
    st.session_state.anki_cards_csv = ""


# Initialize Bot Agents (with history restoration from SQLite DB)
def init_chats():
    current_key = api_keys[st.session_state.key_index]
    st.session_state.client = genai.Client(api_key=current_key)
    target_lang = st.session_state.selected_language

    if "Darja" in target_lang:
        lang_instruction = "IMPORTANT LANGUAGE INSTRUCTION: You MUST speak exclusively in Algerian Darja (الدارجة الجزائرية)."
    else:
        lang_instruction = f"IMPORTANT LANGUAGE INSTRUCTION: You MUST always generate your complete response in {target_lang}."

    # 1. The Chef
    if "Darja" in target_lang:
        chef_system_prompt = (
            "أنت 'The Chef'، شيف ومختص تغذية رياضية في منصة PEKKA. لكنك شخصية مستفزة جداً، ساخرة، وتعرف كيفاش تسب وتنكّت على المستخدم بأسلوب 'Roast' كي يبدأ التمرين أو يحكي معك على الماكولات والجيم. "
            "تضحك عليه كي يكون كسلان، وتعطيه وصفات هاي بروتين بالدارجة الجزائرية مع تكسير راس ومزاح خشن وثقيل. "
            "استعمل الدارجة الجزائرية بامتياز (واش راك يا الكسلان، اطلق يديك، راك تحسب روحك تمرين...). "
            "راجع دائماً سجل المحادثات السابقة لتفهم سياق كلام المستخدم ولا تكرر نفسك."
        )
    else:
        chef_system_prompt = (
            "You are 'The Chef', an elite culinary nutritionist and fitness chef operating within the PEKKA AI suite. "
            "You are extremely provocative, sarcastic, and love to roast and tease the user heavily. Always review past conversation history before answering. "
            f"Always generate your complete response in {target_lang}."
        )

    db_chef_messages = load_messages_from_db("chef")
    chef_history = []
    for m in db_chef_messages:
        chef_history.append(
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part.from_text(text=m["content"])],
            )
        )

    st.session_state.chef_chat = st.session_state.client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(system_instruction=chef_system_prompt),
        history=chef_history if chef_history else None,
    )

    # 2. Sensai
    doc_context = (
        st.session_state.pdf_text
        if st.session_state.pdf_text
        else "No medical document uploaded yet."
    )
    
    quiz_mode_prompt = ""
    if st.session_state.sensai_quiz_mode:
        quiz_mode_prompt = (
            "\n*** CLINICAL QUIZ MODE ACTIVE ***\n"
            "You are acting as an expert medical examiner. Ask the user interactive QCM questions or clinical case scenarios. "
            "Evaluate their answers strictly, explain physiological mechanisms, and challenge them to think like a medical practitioner. "
            "Keep a slightly humorous/sarcastic medical professor tone in Algerian Darja if selected."
        )

    if "Darja" in target_lang:
        sensai_system_prompt = (
            "أنت 'Sensai'، خبير طبي وطبيب ذكي في منصة PEKKA. تتكلم بالدارجة الجزائرية بأسلوب رزين لكن فيه شوية استفزاز وسخرية خفيفة. "
            "راجع تاريخ المحادثة السابقة جيداً قبل الإجابة لتربط التحاليل أو الأعراض السابقة بأسئلة المستخدم الحالية.\n"
            f"{quiz_mode_prompt}\n\n"
            "--- START OF MEDICAL DOCUMENT CONTEXT ---\n"
            f"{doc_context}\n"
            "--- END OF MEDICAL DOCUMENT CONTEXT ---"
        )
    else:
        sensai_system_prompt = (
            "You are 'Sensai', an advanced AI medical knowledge specialist on PEKKA.\n"
            "Always review the past conversation history before responding to maintain medical context.\n"
            f"{quiz_mode_prompt}\n"
            f"{lang_instruction}\n\n"
            "--- START OF MEDICAL DOCUMENT CONTEXT ---\n"
            f"{doc_context}\n"
            "--- END OF MEDICAL DOCUMENT CONTEXT ---"
        )

    db_sensai_messages = load_messages_from_db("sensai")
    sensai_history = []
    for m in db_sensai_messages:
        sensai_history.append(
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part.from_text(text=m["content"])],
            )
        )

    st.session_state.sensai_chat = st.session_state.client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(system_instruction=sensai_system_prompt),
        history=sensai_history if sensai_history else None,
    )

    # 3. Pocoloco
    pocoloco_system_prompt = (
        "You are 'Pocoloco', a fast, witty, highly versatile general-purpose AI assistant on PEKKA. Always review conversation history before answering.\n"
        f"{lang_instruction}"
    )

    db_pocoloco_messages = load_messages_from_db("pocoloco")
    pocoloco_history = []
    for m in db_pocoloco_messages:
        pocoloco_history.append(
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part.from_text(text=m["content"])],
            )
        )

    st.session_state.pocoloco_chat = st.session_state.client.chats.create(
        model="gemini-3.8-flash",
        config=types.GenerateContentConfig(system_instruction=pocoloco_system_prompt),
        history=pocoloco_history if pocoloco_history else None,
    )


if "client" not in st.session_state or "chef_chat" not in st.session_state:
    init_chats()


# Unified Message Dispatcher with Key Rotation, Exponential Backoff & 503 Retry
def send_message_with_rotation(bot_type, prompt_contents):
    attempts = 0
    max_attempts = len(api_keys)
    max_retries = 3

    while attempts < max_attempts:
        try:
            for retry in range(max_retries):
                try:
                    if bot_type == "chef":
                        response = st.session_state.chef_chat.send_message(prompt_contents)
                    elif bot_type == "sensai":
                        response = st.session_state.sensai_chat.send_message(prompt_contents)
                    else:
                        response = st.session_state.pocoloco_chat.send_message(prompt_contents)
                    return response.text
                except Exception as retry_err:
                    if "503" in str(retry_err) and retry < max_retries - 1:
                        time.sleep(2 * (retry + 1))
                        continue
                    else:
                        raise retry_err

        except Exception as e:
            error_str = str(e)
            if (
                "429" in error_str
                or "RESOURCE_EXHAUSTED" in error_str
                or "503" in error_str
                or "closed" in error_str.lower()
            ):
                attempts += 1
                backoff_delay = 2 ** attempts
                
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    st.session_state.key_index = (st.session_state.key_index + 1) % len(api_keys)

                init_chats()
                time.sleep(backoff_delay)

                if attempts >= max_attempts:
                    return "⚠️ تم استنفاد الحد الأقصى لجميع المفاتيح الأربعة مع الانتظار المتصاعد. يرجى الانتظار 10 ثوانٍ والمحاولة مجدداً."
            else:
                return f"Execution Error: {e}"


# ==============================================================================
# 5. LEFT SIDEBAR (PEKKA Navigation Panel)
# ==============================================================================
with st.sidebar:
    st.markdown("## ⚡ PEKKA")
    st.caption("Multi-Agent AI Platform (SQLite Persistent)")
    st.markdown("---")

    active_view = st.radio(
        "Select Active Agent:",
        [
            "The Chef (Gym Nutrition)",
            "Sensai (Medical Expert)",
            "Pocoloco (General AI)",
        ],
        index=0,
    )

    st.markdown("---")
    st.markdown("### 🛠️ Quick Tools")

    if st.button("🗑️ Reset All Conversations"):
        clear_messages_in_db()
        st.session_state.anki_cards_csv = ""
        init_chats()
        st.rerun()

    st.markdown("---")
    st.caption(f"API Key Project: {st.session_state.key_index + 1}/{len(api_keys)}")

# ==============================================================================
# 6. MAIN CONTENT AREA (Header with Top Language Selector)
# ==============================================================================

col_header_title, col_header_lang = st.columns([3, 1])

with col_header_title:
    st.markdown(
        """
        <div style="text-align: left;">
            <div class="app-title">⚡ PEKKA</div>
            <div class="app-subtitle">Next-Generation Specialized AI Workspace</div>
        </div>
    """,
        unsafe_allow_html=True,
    )

with col_header_lang:
    chosen_lang = st.selectbox(
        "🌐 Language / اللغة:",
        [
            "Algerian Darja (الدارجة الجزائرية)",
            "English",
            "Arabic (العربية)",
            "French (Français)",
            "German (Deutsch)",
            "Italian (Italiano)",
            "Spanish (Español)",
        ],
        index=0,
    )

    if chosen_lang != st.session_state.selected_language:
        st.session_state.selected_language = chosen_lang
        init_chats()
        st.toast(f"Language updated to {chosen_lang}!", icon="🌐")

st.markdown("---")

# ------------------------------------------------------------------------------
# VIEW 1: THE CHEF
# ------------------------------------------------------------------------------
if "Chef" in active_view:
    st.markdown(
        '<div class="chef-card-header">👨‍🍳 The Chef — High-Protein Recipes & Gym Nutrition</div>',
        unsafe_allow_html=True,
    )

    col_chef_controls, col_chef_preview = st.columns([1.2, 3])
    with col_chef_controls:
        with st.popover("📸 Upload Meal Photo"):
            uploaded_meal_img = st.file_uploader(
                "Upload meal image for macro analysis",
                type=["jpg", "jpeg", "png"],
                key="meal_img_uploader",
            )

    with col_chef_preview:
        if uploaded_meal_img is not None:
            st.image(uploaded_meal_img, caption="Uploaded Meal Photo", width=220)

    chef_container = st.container(height=450)
    with chef_container:
        db_chef_msgs = load_messages_from_db("chef")
        for msg in db_chef_msgs:
            with st.chat_message(msg["role"]):
                st.markdown(f'<div dir="auto">{msg["content"]}</div>', unsafe_allow_html=True)

    if chef_input := st.chat_input("قول للشيف راني رايح نخدم ليصال ولا حطلي وصفة...", key="chef_input_key"):
        save_message_to_db("chef", "user", chef_input)

        if uploaded_meal_img is not None:
            try:
                img = Image.open(uploaded_meal_img)
                contents_to_send = [img, chef_input]
            except Exception as img_err:
                st.error(f"Image load error: {img_err}")
                contents_to_send = chef_input
        else:
            contents_to_send = chef_input

        with chef_container:
            with st.chat_message("user"):
                st.markdown(f'<div dir="auto">{chef_input}</div>', unsafe_allow_html=True)
            with st.chat_message("assistant"):
                with st.spinner("The Chef راه يتقهوى ويبعث في الرد المستفز..."):
                    answer = send_message_with_rotation("chef", contents_to_send)
                    save_message_to_db("chef", "assistant", answer)
                    st.markdown(f'<div dir="auto">{answer}</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------------------
# VIEW 2: SENSAI (Medical Focus & Anki / QCM Generator)
# ------------------------------------------------------------------------------
elif "Sensai" in active_view:
    st.markdown(
        '<div class="sensai-card-header">🩺 Sensai — Medical Knowledge & Clinical PDF Expert</div>',
        unsafe_allow_html=True,
    )

    col_s1, col_s2, col_s3 = st.columns([1.5, 1, 1])

    with col_s1:
        with st.popover("📎 Upload Medical PDF / Clinical Report"):
            uploaded_file = st.file_uploader("Upload Medical PDF", type=["pdf"], key="sensai_pdf_uploader")
            if uploaded_file is not None:
                if st.button("🚀 Analyze Medical Document", key="process_sensai_pdf"):
                    with st.spinner("Sensai is reviewing clinical document text..."):
                        try:
                            pdf_reader = PdfReader(uploaded_file)
                            extracted_text = ""
                            for page in pdf_reader.pages:
                                text = page.extract_text()
                                if text:
                                    extracted_text += text + "\n"

                            st.session_state.pdf_text = extracted_text
                            init_chats()
                            clear_messages_in_db("sensai")
                            st.success("Medical document loaded successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Document processing error: {e}")

    with col_s2:
        quiz_toggle = st.toggle("🩺 Mode QCM & Clinical Cases", value=st.session_state.sensai_quiz_mode)
        if quiz_toggle != st.session_state.sensai_quiz_mode:
            st.session_state.sensai_quiz_mode = quiz_toggle
            init_chats()
            st.toast("QCM & Clinical Quiz Mode Updated!", icon="🧠")

    with col_s3:
        if st.button("🎴 Generate Anki Cards"):
            db_sensai_check = load_messages_from_db("sensai")
            if not db_sensai_check and not st.session_state.pdf_text:
                st.warning("رجاءً قم برفع ملف PDF أو اطرح أسئلة طبية أولاً لتوليد بطاقات Anki!")
            else:
                with st.spinner("Sensai راه يوجد في بطاقات Anki CSV..."):
                    anki_prompt = (
                        "Generate a list of 5-10 high-yield Anki flashcards based on our current chat history and uploaded medical PDF. "
                        "Format strictly as CSV with two columns separated by a comma (no headers): Question,Answer. "
                        "Keep answers concise, precise, and ideal for medical spaced repetition."
                    )
                    anki_res = send_message_with_rotation("sensai", anki_prompt)
                    st.session_state.anki_cards_csv = anki_res
                    st.success("تم توليد بطاقات Anki بنجاح!")

    if st.session_state.anki_cards_csv:
        st.download_button(
            label="📥 Download Anki Flashcards (.csv)",
            data=st.session_state.anki_cards_csv,
            file_name="pekka_medical_anki_cards.csv",
            mime="text/csv",
            key="download_anki_csv_btn",
        )

    if not st.session_state.pdf_text:
        st.info("💡 Sensai جاهز للأسئلة الطبية، مراجعة QCM، أو تحليل ملفات PDF للدروس والتحاليل.")

    sensai_container = st.container(height=420)
    with sensai_container:
        db_sensai_msgs = load_messages_from_db("sensai")
        for msg in db_sensai_msgs:
            with st.chat_message(msg["role"]):
                st.markdown(f'<div dir="auto">{msg["content"]}</div>', unsafe_allow_html=True)

    if sensai_input := st.chat_input(
        "سقسي سينساي على الأعراض، التحاليل الطبية ولا الوثائق المرفوقة...",
        key="sensai_input_key",
    ):
        save_message_to_db("sensai", "user", sensai_input)
        with sensai_container:
            with st.chat_message("user"):
                st.markdown(f'<div dir="auto">{sensai_input}</div>', unsafe_allow_html=True)
            with st.chat_message("assistant"):
                with st.spinner("Sensai راه يحلل في المعطيات الطبية..."):
                    answer = send_message_with_rotation("sensai", sensai_input)
                    save_message_to_db("sensai", "assistant", answer)
                    st.markdown(f'<div dir="auto">{answer}</div>', unsafe_allow_html=True)

    db_sensai_msgs_export = load_messages_from_db("sensai")
    sensai_answers = "\n\n-------------------------\n\n".join([
        f"Sensai:\n{msg['content']}"
        for msg in db_sensai_msgs_export
        if msg["role"] == "assistant"
    ])
    if sensai_answers:
        st.download_button(
            label="📥 Export Medical Notes (TXT)",
            data=sensai_answers,
            file_name="sensai_medical_notes.txt",
            mime="text/plain",
            key="download_sensai_btn",
        )

# ------------------------------------------------------------------------------
# VIEW 3: POCOLOCO
# ------------------------------------------------------------------------------
elif "Pocoloco" in active_view:
    st.markdown(
        '<div class="pocoloco-card-header">🤪 Pocoloco — General AI Assistant</div>',
        unsafe_allow_html=True,
    )

    pocoloco_container = st.container(height=480)
    with pocoloco_container:
        db_pocoloco_msgs = load_messages_from_db("pocoloco")
        for msg in db_pocoloco_msgs:
            with st.chat_message(msg["role"]):
                st.markdown(f'<div dir="auto">{msg["content"]}</div>', unsafe_allow_html=True)

    if pocoloco_input := st.chat_input("Ask Pocoloco anything...", key="pocoloco_input_key"):
        save_message_to_db("pocoloco", "user", pocoloco_input)
        with pocoloco_container:
            with st.chat_message("user"):
                st.markdown(f'<div dir="auto">{pocoloco_input}</div>', unsafe_allow_html=True)
            with st.chat_message("assistant"):
                with st.spinner("Pocoloco is responding..."):
                    answer = send_message_with_rotation("pocoloco", pocoloco_input)
                    save_message_to_db("pocoloco", "assistant", answer)
                    st.markdown(f'<div dir="auto">{answer}</div>', unsafe_allow_html=True)
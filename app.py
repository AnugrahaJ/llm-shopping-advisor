"""
Willy — the LLM Shopping Advisor chat app.

Run it with:
    streamlit run app.py

Four stages, held in st.session_state.stage:
    welcome  -> the landing screen
    chat     -> Willy asks the follow-up questions, one at a time
    summary  -> Willy shows what he understood and asks her to confirm
    results  -> the recommendation, with a View product button when there is a link

Willy calls run_v2_7 from bot.py, which returns an answer with the product
link in it. extract_links pulls the URL out. No link means no button, which
is correct for a refusal.
"""

import os
import html
import base64

import streamlit as st
from langchain_core.messages import SystemMessage, HumanMessage

from bot import llm, detect_category_2, run_v2_7, extract_links, OUT_OF_SCOPE_REPLY


# ===== the question lists =====
# (key, what Willy says, short label for the summary card)

SKINCARE_QUESTIONS = [
    ("skin_type",
     "What's your skin type — oily, dry, combination, or not sure?",
     "Skin type"),
    ("concern",
     "What's the main thing you'd like it to help with?",
     "Main concern"),
    ("budget",
     "What's your budget? If you're not sure, just say so and I'll suggest a range.",
     "Budget"),
    ("allergies",
     "Any allergies or sensitivities, or anything a dermatologist has told you to avoid?",
     "Allergies"),
    ("current_routine",
     "What does your current routine look like? If you don't have one, that's fine too.",
     "Current routine"),
]

DIET_QUESTIONS = [
    ("safety",
     "First, something important: are you pregnant, taking any medication, "
     "or managing a medical condition?",
     "Health notes"),
    ("goal",
     "What's your goal — weight loss, weight gain, or just eating better?",
     "Goal"),
    ("allergies",
     "Any food allergies I should know about?",
     "Allergies"),
    ("meal_or_snack",
     "Will this replace a meal, or is it a snack on top of your meals?",
     "Meal or snack"),
    ("budget",
     "What's your budget? If you're not sure, just say so and I'll suggest a range.",
     "Budget"),
]


# ===== Willy's faces =====

AVATARS = {
    "neutral": "assets/neutral.png",
    "thinking": "assets/thinking.png",
    "happy": "assets/happy.png",
    "concerned": "assets/concerned.png",
    "surprised": "assets/surprised.png",
    "apologetic": "assets/apologetic.png",
}

# Base names only. find_image() tries the usual extensions, so it does not
# matter whether you saved them as .png, .jpg or .webp.

CATEGORY_IMAGES = {
    "skincare": "assets/skincare",
    "diet_foods": "assets/food",
}

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

# The big header portrait. Falls back to the normal happy face if the
# large one isn't there.

HEADER_IMAGE_BASES = ("assets/happy_large", "assets/happy")


def find_image(base):
    """First file that exists among base.png, base.jpg, base.jpeg, base.webp."""
    for ext in IMAGE_EXTENSIONS:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    return None


def face(mood):
    """Avatar path if the file is there, otherwise an emoji."""
    path = AVATARS.get(mood)
    if path and os.path.exists(path):
        return path
    return "🧴"


def data_uri(path):
    """Read an image off disk and turn it into a data URI.
    The type comes from the file's own first bytes, not its name, so a PNG
    saved as .jpg still renders."""
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        raw = f.read()
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        mime = "png"
    elif raw[:3] == b"\xff\xd8\xff":
        mime = "jpeg"
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        mime = "webp"
    else:
        mime = "png"
    return f"data:image/{mime};base64," + base64.b64encode(raw).decode()


# ===== the diet-foods hard stop =====

SAFETY_CHECK_RULES = SystemMessage(
    "A shopper was asked: are you pregnant, on medication, or managing a "
    "medical condition?\n"
    "Read her answer and reply with ONE word only:\n"
    "- STOP if she has any condition, medication or pregnancy and has NOT said "
    "a doctor approved this kind of product.\n"
    "- APPROVED if she has a condition but says her doctor has approved it.\n"
    "- CLEAR if she has none of these.\n"
    "No punctuation, no explanation."
)


def safety_verdict(answer_text):
    """Returns 'STOP', 'APPROVED' or 'CLEAR'."""
    reply = llm.invoke([SAFETY_CHECK_RULES, HumanMessage(answer_text)])
    text = reply.content.strip().upper()
    for word in ("APPROVED", "STOP", "CLEAR"):
        if word in text:
            return word
    return "STOP"


DOCTOR_STOP_REPLY = (
    "Thanks for telling me that. Because of this, I'd rather not suggest a "
    "product for you — foods and supplements can affect medication and medical "
    "conditions in ways a doctor needs to weigh up.\n\n"
    "Please talk to your doctor first. If they've already approved this kind of "
    "product for you, just say so and I'll be glad to help."
)


# ===== which face Willy wears on the answer =====
# A deterministic guess from the answer text. No extra LLM call, so no tokens.
# Tune the word lists if a face shows up in the wrong place.

CLAIM_FAILED_WORDS = (
    "doesn't hold", "does not hold", "hidden sugar", "still contains sugar",
    "contains sugar", "can't confirm", "cannot confirm", "not sugar-free",
    "despite the claim", "front of the pack", "front-of-pack",
)

DOCTOR_WORDS = (
    "doctor", "pregnan", "medication", "medicinal", "prescription", "dermatologist has",
)


def mood_for_answer(text, links):
    """happy / surprised when there is a product, concerned / apologetic when there isn't."""
    low = (text or "").lower()
    if not links:
        if any(w in low for w in DOCTOR_WORDS):
            return "concerned"
        return "apologetic"
    if any(w in low for w in CLAIM_FAILED_WORDS):
        return "surprised"
    return "happy"


# ===== session state =====

DEFAULTS = {
    "stage": "welcome",
    "messages": [],
    "answers": {},
    "category": None,
    "request": None,
    "pending_key": None,
    "answer_text": None,
    "answer_links": [],
    "question_no": 0,
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value.copy() if isinstance(value, (dict, list)) else value


def say(text, mood="neutral", label=None):
    """Add one of Willy's messages to the chat."""
    st.session_state.messages.append(
        {"role": "assistant", "mood": mood, "content": text, "label": label}
    )


def questions():
    if st.session_state.category == "skincare":
        return SKINCARE_QUESTIONS
    return DIET_QUESTIONS


def label_for(key):
    for k, _text, label in questions():
        if k == key:
            return label
    return key


def next_question():
    """First question she hasn't answered, or (None, None) when they're done."""
    for key, text, _label in questions():
        if key not in st.session_state.answers:
            return key, text
    return None, None


def ask_next_or_summarise():
    """Ask the next question, or move to the summary screen."""
    key, text = next_question()

    if key is not None:
        st.session_state.pending_key = key
        st.session_state.question_no += 1
        say(text, "neutral", label=f"WILLY · QUESTION {st.session_state.question_no:02d}")
        return

    st.session_state.pending_key = None
    say("I've got a better idea of what you're looking for. Here's what I've understood:",
        "happy")
    st.session_state.stage = "summary"


def run_search():
    """Call the bot and store the answer plus any link."""
    try:
        _category, _query, answer = run_v2_7(
            st.session_state.request, st.session_state.answers
        )
    except Exception as e:
        st.session_state.answer_text = f"Something went wrong while searching: {e}"
        st.session_state.answer_links = []
        st.session_state.stage = "results"
        return

    st.session_state.answer_text = answer
    st.session_state.answer_links = extract_links(answer)
    st.session_state.stage = "results"


def reset(keep_stage="chat"):
    st.session_state.answers = {}
    st.session_state.category = None
    st.session_state.request = None
    st.session_state.pending_key = None
    st.session_state.answer_text = None
    st.session_state.answer_links = []
    st.session_state.question_no = 0
    st.session_state.messages = []
    st.session_state.stage = keep_stage


# ===== the page =====

st.set_page_config(
    page_title="Willy — your personal purchase assistant",
    page_icon="🧴",
    layout="wide",
)

CREAM = "#F4EBDD"
IVORY = "#FFFDF8"
NAVY = "#243A59"
CHARCOAL = "#344052"
DUSTY_BLUE = "#71849B"
ROSE = "#C58A9F"
BERRY = "#A95778"
BEIGE = "#E5D7C9"

st.markdown(
    f"""
    <link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
      [data-testid="stAppViewContainer"] {{ background: {CREAM}; }}
      [data-testid="stHeader"] {{ background: transparent; }}
      .block-container {{ max-width: 1080px; padding-top: 1.5rem; padding-bottom: 6rem; }}
      html, body, .stApp, p, li, div, span, label, input, textarea {{ font-family: 'Inter', sans-serif; }}
      h1, h2, h3, [data-testid="stHeading"] h1, [data-testid="stHeading"] h2, [data-testid="stHeading"] h3 {{ font-family: 'Fraunces', serif !important; font-weight: 700 !important; color: {NAVY} !important; }}
      .hdr {{ display: flex; align-items: center; justify-content: center; gap: 18px; }}
      .hdr-text {{ text-align: left; }}
      .willy-name {{ font-family: 'Fraunces', serif; font-weight: 700; color: {NAVY}; line-height: 1; margin: 0; }}
      .willy-sub {{ color: {DUSTY_BLUE}; margin: 0.25rem 0 0; }}
      .willy-rule {{ width: 88px; height: 2px; background: {ROSE}; margin: 1.1rem auto; border-radius: 2px; }}
      .willy-h2 {{ font-family: 'Fraunces', serif; font-weight: 700; font-size: 2.6rem; color: {NAVY}; text-align: center; margin: 0; line-height: 1.2; }}
      .willy-center {{ width: 100%; text-align: center; }}
      .willy-lede {{ display: inline-block; font-size: 1.05rem; color: {CHARCOAL}; line-height: 1.75; text-align: center; max-width: 640px; margin: 0.8rem 0 0; }}
      .willy-label {{ font-size: 0.82rem; font-weight: 600; color: {NAVY}; margin: 0.6rem 0 0.1rem 3.3rem; }}
      .you-label {{ font-size: 0.82rem; font-weight: 600; color: {DUSTY_BLUE}; text-align: right; margin: 1rem 0.3rem 0.25rem 0; }}
      .you-bubble {{ background: {NAVY}; color: {IVORY}; border-radius: 18px 18px 6px 18px; padding: 13px 18px; max-width: 62%; margin-left: auto; font-size: 0.95rem; line-height: 1.7; width: fit-content; }}
      .cat-card {{ background: {IVORY}; border: 1px solid {ROSE}; border-radius: 16px; padding: 14px; height: 100%; }}
      .cat-card img {{ width: 100%; height: 230px; object-fit: cover; border-radius: 12px; display: block; }}
      .cat-ph {{ width: 100%; height: 230px; border-radius: 10px; background: #EFE6DA; display: flex; align-items: center; justify-content: center; color: {DUSTY_BLUE}; font-size: 0.8rem; }}
      .cat-title {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.45rem; color: {NAVY}; margin-top: 12px; }}
      .cat-desc {{ font-size: 0.95rem; color: {DUSTY_BLUE}; line-height: 1.6; }}
      .helps {{ background: {IVORY}; border: 1px solid {BEIGE}; border-radius: 16px; padding: 20px 24px; margin-top: 20px; }}
      .helps-title {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.45rem; color: {NAVY}; margin-bottom: 6px; }}
      .helps li {{ font-size: 1rem; color: {CHARCOAL}; line-height: 2.1; }}
      .qlabel {{ font-size: 0.7rem; letter-spacing: 0.08em; color: {BERRY}; font-weight: 600; margin: 0 0 4px 52px; }}
      .summary-card {{ background: {IVORY}; border: 1px solid {BEIGE}; border-radius: 14px; padding: 18px 22px; margin-top: 10px; }}
      .summary-title {{ font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.45rem; color: {NAVY}; margin-bottom: 10px; }}
      .summary-row {{ display: flex; justify-content: space-between; gap: 20px; padding: 8px 0; border-bottom: 1px solid {BEIGE}; font-size: 0.92rem; }}
      .summary-row:last-child {{ border-bottom: none; }}
      .summary-key {{ color: {DUSTY_BLUE}; }}
      .summary-val {{ color: {NAVY}; font-weight: 500; text-align: right; }}
      .answer-card {{ background: {IVORY}; border: 1px solid {BEIGE}; border-radius: 14px; padding: 18px 22px; }}
      .answer-flag {{ font-size: 0.7rem; letter-spacing: 0.08em; color: {BERRY}; font-weight: 600; margin-bottom: 8px; }}
      [data-testid="stChatMessage"] {{ background: {IVORY}; border: none; border-radius: 18px 18px 18px 6px; padding: 14px 20px; margin-bottom: 10px; max-width: 82%; width: fit-content; box-shadow: none; }}
      [data-testid="stChatMessage"] p {{ font-size: 0.95rem; line-height: 1.7; color: {CHARCOAL}; }}
      [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {{ background: {NAVY}; border-radius: 18px 18px 6px 18px; margin-left: auto; }}
      [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) p {{ color: {IVORY}; }}
      [data-testid="stChatMessageAvatarImage"] {{ border-radius: 50%; background: transparent; }}
      [data-testid="stChatInput"] {{ background: {IVORY}; border: 1px solid {BEIGE}; border-radius: 16px; }}
      [data-testid="stChatInputTextArea"] {{ font-size: 0.95rem; }}
      .stButton > button, .stLinkButton > a {{ background: {NAVY}; color: {IVORY} !important; border: none; border-radius: 12px; padding: 0.8rem 1.6rem; font-weight: 600; font-size: 1.05rem; }}
      .stButton > button:hover, .stLinkButton > a:hover {{ background: #1b2c45; color: {IVORY} !important; }}
      a {{ color: #378D94; }}
      hr {{ border: none; height: 1px; background: {BEIGE}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def header_image():
    """The big portrait, preferring assets/happy_large if it exists."""
    for base in HEADER_IMAGE_BASES:
        uri = data_uri(find_image(base))
        if uri:
            return uri
    return None


def header(big=True):
    """Willy's face beside his name, with the pink rule underneath."""
    size = 92 if big else 56
    name_size = 3.6 if big else 2.1
    sub_size = 1.0 if big else 0.85
    uri = header_image()
    img = (f'<img src="{uri}" width="{size}" style="display:block;">' if uri else "")
    st.markdown(
        f'<div class="hdr">{img}<div class="hdr-text">'
        f'<p class="willy-name" style="font-size:{name_size}rem;">Willy</p>'
        f'<p class="willy-sub" style="font-size:{sub_size}rem;">Your personal purchase assistant</p>'
        f'</div></div><div class="willy-rule"></div>',
        unsafe_allow_html=True,
    )


def category_card(title, desc, image_key):
    uri = data_uri(find_image(CATEGORY_IMAGES[image_key]))
    picture = (f'<img src="{uri}">' if uri
               else '<div class="cat-ph">add the photo to assets/</div>')
    st.markdown(
        f'<div class="cat-card">{picture}'
        f'<div class="cat-title">{title}</div>'
        f'<div class="cat-desc">{desc}</div></div>',
        unsafe_allow_html=True,
    )


# ===== stage 1: welcome =====

if st.session_state.stage == "welcome":
    header(big=True)
    st.markdown(
        '<div class="willy-center">'
        '<p class="willy-h2">Find products that suit you.</p>'
        '<p class="willy-lede">Discover skincare and diet-friendly food products '
        'based on your needs, preferences and budget. I read the ingredients list '
        'so you don\'t have to.</p>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.write("")
    left, right = st.columns(2, gap="medium")
    with left:
        category_card("Skincare",
                      "Find products for your skin type and concerns.",
                      "skincare")
    with right:
        category_card("Diet-friendly food",
                      "Navigate packaged food choices and find what fits.",
                      "diet_foods")

    st.markdown(
        '<div class="helps"><div class="helps-title">What Willy helps you do</div>'
        '<ul><li>Get a recommendation built around your own answers</li>'
        '<li>Check whether a label claim actually holds up</li>'
        '<li>Hear it plainly when a product isn\'t right for you</li></ul></div>',
        unsafe_allow_html=True,
    )

    st.write("")
    if st.button("Get started", use_container_width=True):
        reset(keep_stage="chat")
        say("Hi, I'm Willy. I help with **skincare** and **diet foods**, and I'll be "
            "honest with you — if a \"zero sugar\" or \"brightening\" claim doesn't "
            "hold up, I'll say so.\n\nSo, what are you looking at?", "happy")
        st.rerun()


# ===== stages 2, 3, 4 share the compact header and the conversation =====

else:
    header(big=False)

    for m in st.session_state.messages:
        if m["role"] == "assistant":
            if m.get("label"):
                st.markdown(f'<p class="qlabel">{m["label"]}</p>', unsafe_allow_html=True)
            else:
                st.markdown('<p class="willy-label">Willy</p>', unsafe_allow_html=True)
            with st.chat_message("assistant", avatar=face(m["mood"])):
                st.markdown(m["content"])
        else:
            # Her messages are drawn by hand. st.chat_message would force
            # Streamlit's own red default avatar, which we don't want.
            text = html.escape(m["content"]).replace("\n", "<br>")
            st.markdown(
                f'<p class="you-label">You</p><div class="you-bubble">{text}</div>',
                unsafe_allow_html=True,
            )

    # ----- stage 3: the preference summary -----

    if st.session_state.stage == "summary":
        rows = ""
        for key, _text, label in questions():
            value = st.session_state.answers.get(key, "")
            rows += (f'<div class="summary-row"><span class="summary-key">{label}</span>'
                     f'<span class="summary-val">{value}</span></div>')
        heading = ("Your skincare preferences" if st.session_state.category == "skincare"
                   else "Your diet food preferences")
        st.markdown(
            f'<div class="summary-card"><div class="summary-title">{heading}</div>'
            f'{rows}</div>',
            unsafe_allow_html=True,
        )
        st.write("")

        if st.button("Yes, find my matches", use_container_width=True):
            with st.spinner("Looking through the shops..."):
                run_search()
            st.rerun()

        with st.expander("I want to change something"):
            labels = {label: key for key, _text, label in questions()}
            choice = st.selectbox("Which answer?", list(labels.keys()))
            if st.button("Change this answer"):
                key = labels[choice]
                st.session_state.answers.pop(key, None)
                st.session_state.stage = "chat"
                ask_next_or_summarise()
                st.rerun()

    # ----- stage 4: the recommendation -----

    elif st.session_state.stage == "results":
        links = st.session_state.answer_links
        mood = mood_for_answer(st.session_state.answer_text, links)
        flag = ("CHECKED AGAINST YOUR ANSWERS" if links else "NO PRODUCT RECOMMENDED")
        st.markdown(f'<div class="answer-flag">{flag}</div>', unsafe_allow_html=True)
        with st.chat_message("assistant", avatar=face(mood)):
            st.markdown(st.session_state.answer_text or "")

        if links:
            st.link_button("View product", links[0])

        st.write("")
        if st.button("Ask about something else"):
            reset(keep_stage="chat")
            say("Sure — what are you looking for?", "neutral")
            st.rerun()

    # ----- the input box, on the chat and results stages -----

    if st.session_state.stage in ("chat", "results"):
        placeholder = ("Type your answer..." if st.session_state.pending_key
                       else "Message Willy...")
        user_text = st.chat_input(placeholder)

        if user_text:
            st.session_state.messages.append({"role": "user", "content": user_text})

            # no category yet: this is her opening request
            if st.session_state.category is None:
                with st.spinner("Thinking..."):
                    category = detect_category_2(user_text)

                if category == "other":
                    say(OUT_OF_SCOPE_REPLY, "apologetic")
                else:
                    st.session_state.category = category
                    st.session_state.request = user_text
                    say("Got it. A few quick questions first.", "thinking")
                    ask_next_or_summarise()

            # she's answering a question
            elif st.session_state.pending_key is not None:
                key = st.session_state.pending_key
                st.session_state.answers[key] = user_text

                stopped = False
                if st.session_state.category == "diet_foods" and key == "safety":
                    with st.spinner("Thinking..."):
                        verdict = safety_verdict(user_text)

                    if verdict == "STOP":
                        say(DOCTOR_STOP_REPLY, "concerned")
                        st.session_state.pending_key = None
                        st.session_state.answer_text = DOCTOR_STOP_REPLY
                        st.session_state.answer_links = []
                        st.session_state.stage = "results"
                        stopped = True
                    elif verdict == "APPROVED":
                        st.session_state.answers[key] = (
                            user_text
                            + " (she says her doctor has approved this kind of product)"
                        )

                if not stopped:
                    ask_next_or_summarise()

            # she's typed something after the answer was given
            else:
                request = user_text
                reset(keep_stage="chat")
                st.session_state.messages.append({"role": "user", "content": request})
                with st.spinner("Thinking..."):
                    category = detect_category_2(request)

                if category == "other":
                    say(OUT_OF_SCOPE_REPLY, "apologetic")
                else:
                    st.session_state.category = category
                    st.session_state.request = request
                    say("Got it. A few quick questions first.", "thinking")
                    ask_next_or_summarise()

            st.rerun()

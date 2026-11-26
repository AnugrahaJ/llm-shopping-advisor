"""
Willy — the LLM Shopping Advisor chat app.

Run it with:
    streamlit run app.py

Willy asks the follow-up questions one at a time, remembers the answers,
then calls run_v2_6 from bot.py to search and answer.
"""

import os
import urllib.parse

import streamlit as st
from langchain_core.messages import SystemMessage, HumanMessage

from bot import llm, detect_category_2, run_v2_6, OUT_OF_SCOPE_REPLY


# ===== the question lists =====
# Each item is (key, what Willy says). The key is what goes in the answers dict.

SKINCARE_QUESTIONS = [
    ("skin_type",
     "What's your skin type — oily, dry, combination, or not sure?"),
    ("concern",
     "What's the main thing you'd like it to help with?"),
    ("budget",
     "What's your budget? If you're not sure, just say so and I'll suggest a range."),
    ("allergies",
     "Any allergies or sensitivities, or anything a dermatologist has told you to avoid?"),
    ("current_routine",
     "What does your current routine look like? If you don't have one, that's fine too."),
]

DIET_QUESTIONS = [
    ("safety",
     "First, something important: are you pregnant, taking any medication, "
     "or managing a medical condition?"),
    ("goal",
     "What's your goal — weight loss, weight gain, or just eating better?"),
    ("allergies",
     "Any food allergies I should know about?"),
    ("meal_or_snack",
     "Will this replace a meal, or is it a snack on top of your meals?"),
    ("budget",
     "What's your budget? If you're not sure, just say so and I'll suggest a range."),
]


# ===== Willy's faces =====

AVATARS = {
    "neutral": "assets/neutral.png",
    "thinking": "assets/thinking.png",
    "happy": "assets/happy.png",
    "concerned": "assets/concerned.png",
    "surprised": "assets/surprised.png",
    "apologetic": "assets/apologetic.png",
    "you": "assets/you.png",          # her own avatar
}


def face(mood):
    """Return the avatar path if the file exists, otherwise fall back to an emoji."""
    path = AVATARS.get(mood)
    if path and os.path.exists(path):
        return path
    return "🧑" if mood == "you" else "🧴"


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
    return "STOP"          # if unsure, be careful


DOCTOR_STOP_REPLY = (
    "Thanks for telling me that. Because of this, I'd rather not suggest a "
    "product for you — foods and supplements can affect medication and medical "
    "conditions in ways a doctor needs to weigh up.\n\n"
    "Please talk to your doctor first. If they've already approved this kind of "
    "product for you, just say so and I'll be glad to help."
)


# ===== session state: what Willy remembers between messages =====

if "messages" not in st.session_state:
    st.session_state.messages = []          # the chat on screen
if "answers" not in st.session_state:
    st.session_state.answers = {}           # her follow-up answers
if "category" not in st.session_state:
    st.session_state.category = None        # skincare / diet_foods
if "request" not in st.session_state:
    st.session_state.request = None         # her original message
if "pending_key" not in st.session_state:
    st.session_state.pending_key = None     # the question Willy just asked
if "finished" not in st.session_state:
    st.session_state.finished = False


def say(text, mood="neutral"):
    """Add one of Willy's messages to the chat."""
    st.session_state.messages.append(
        {"role": "assistant", "mood": mood, "content": text}
    )


def questions():
    if st.session_state.category == "skincare":
        return SKINCARE_QUESTIONS
    return DIET_QUESTIONS


def next_question():
    """The first question she hasn't answered yet, or None if they're all done."""
    for key, text in questions():
        if key not in st.session_state.answers:
            return key, text
    return None, None


def ask_next_or_answer():
    """Either ask the next question, or search and give the recommendation."""
    key, text = next_question()

    if key is not None:
        st.session_state.pending_key = key
        say(text, "neutral")
        return

    # all questions answered — go and search.
    # Willy's thinking face sits on screen while that happens.
    st.session_state.pending_key = None

    waiting = st.empty()
    with waiting.container():
        with st.chat_message("assistant", avatar=face("thinking")):
            st.markdown("_Looking through the shops..._")

    try:
        category, query, answer = run_v2_6(
            st.session_state.request, st.session_state.answers
        )
    except Exception as e:
        waiting.empty()
        say(f"Something went wrong while searching: {e}", "concerned")
        st.session_state.finished = True
        return

    waiting.empty()          # take the thinking face away
    say(answer, "happy")
    st.session_state.finished = True


def reset():
    st.session_state.answers = {}
    st.session_state.category = None
    st.session_state.request = None
    st.session_state.pending_key = None
    st.session_state.finished = False


# ===== the screen =====

st.set_page_config(
    page_title="Willy — Shopping Advisor",
    page_icon="🧴",
    layout="wide",
)

# the lavender background with its blobs and teal leaves
BACKGROUND_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 900"'
    ' preserveAspectRatio="xMidYMid slice">'
    '<rect width="1200" height="900" fill="#ECE8F6"/>'
    '<path d="M0,0 C180,60 270,0 390,90 C510,180 270,240 90,195 C-30,165 -15,60 0,0 Z"'
    ' fill="#D1CBE5" opacity="0.55"/>'
    '<path d="M1200,0 C1050,45 990,165 1080,255 C1170,345 1230,180 1200,0 Z"'
    ' fill="#D1CBE5" opacity="0.45"/>'
    '<path d="M0,900 C150,840 210,710 90,660 C-15,620 -15,810 0,900 Z"'
    ' fill="#D1CBE5" opacity="0.5"/>'
    '<path d="M1200,900 C1050,870 960,760 1050,700 C1140,640 1230,760 1200,900 Z"'
    ' fill="#9671BD" opacity="0.18"/>'
    '<path d="M930,45 C1020,105 1080,60 1170,105" stroke="#9671BD" stroke-width="2"'
    ' fill="none" opacity="0.55"/>'
    '<g opacity="0.5" fill="#77B5B6">'
    '<ellipse cx="1122" cy="87" rx="24" ry="10" transform="rotate(-28 1122 87)"/>'
    '<ellipse cx="1158" cy="129" rx="24" ry="10" transform="rotate(18 1158 129)"/>'
    '<ellipse cx="1095" cy="138" rx="21" ry="9" transform="rotate(42 1095 138)"/>'
    '</g>'
    '<g opacity="0.45" fill="#77B5B6">'
    '<ellipse cx="60" cy="755" rx="27" ry="12" transform="rotate(34 60 755)"/>'
    '<ellipse cx="108" cy="800" rx="24" ry="10" transform="rotate(-20 108 800)"/>'
    '<ellipse cx="45" cy="820" rx="21" ry="9" transform="rotate(62 45 820)"/>'
    '</g>'
    '</svg>'
)
BACKGROUND_URI = "data:image/svg+xml," + urllib.parse.quote(BACKGROUND_SVG, safe="")

st.markdown(
    f"""
    <link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
      [data-testid="stAppViewContainer"] {{
          background-image: url("{BACKGROUND_URI}");
          background-size: cover;
          background-attachment: fixed;
      }}
      [data-testid="stHeader"] {{ background: transparent; }}
      .block-container {{
          max-width: 920px;
          padding-top: 7rem;
          padding-bottom: 6rem;
      }}
      html, body, .stApp, p, li, div, span, label, input, textarea {{
          font-family: 'Nunito', sans-serif;
      }}
      [data-testid="stChatMessage"] {{
          background: #FFFFFF;
          border: none;
          border-radius: 18px 18px 18px 6px;
          padding: 14px 20px;
          margin-bottom: 14px;
          max-width: 80%;
          width: fit-content;
          box-shadow: 0 1px 3px rgba(106, 64, 141, 0.07);
      }}
      [data-testid="stChatMessage"] p {{
          font-size: 16px;
          line-height: 1.7;
          color: #2A2235;
      }}
      [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {{
          background: #AED5D5;
          border-radius: 18px 18px 6px 18px;
          margin-left: auto;
      }}
      [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) p {{
          color: #153B3D;
      }}
      [data-testid="stChatMessageAvatarImage"] {{
          border-radius: 50%;
          border: 2px solid #FFFFFF;
          background: #D8D1EC;
      }}
      [data-testid="stChatInput"] {{
          background: #FFFFFF;
          border: none;
          border-radius: 18px;
      }}
      [data-testid="stChatInputTextArea"] {{ font-size: 16px; }}
      h1, [data-testid="stHeading"] h1 {{
          font-family: 'Nunito', sans-serif;
          font-weight: 700;
          font-size: 2.6rem;
          color: #6A408D !important;
          margin-bottom: 0rem;
          padding-top: 0.5rem;
      }}
      [data-testid="stCaptionContainer"] p {{
          font-size: 15px;
          color: #9671BD;
      }}
      hr {{
          border: none;
          height: 2px;
          background: #C9BFE0;
          border-radius: 2px;
          opacity: 1;
      }}
      table {{ font-size: 15px; }}
      a {{ color: #378D94; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# header: Willy's smiling face next to his name
header_left, header_right = st.columns([1, 7], vertical_alignment="center")
with header_left:
    happy_face = AVATARS["happy"]
    if os.path.exists(happy_face):
        st.image(happy_face, width=90)
with header_right:
    st.title("Willy")
    st.caption("Your skincare and food label checker")

st.divider()

# Willy's opening line, only once
if not st.session_state.messages:
    say(
        "Hi, I'm Willy 👋\n\n"
        "I read the ingredients list so you don't have to. I help with "
        "**skincare** and **diet foods** — and I'll be honest with you. If a "
        "\"zero sugar\" or \"brightening\" claim doesn't hold up, I'll say so. "
        "If something isn't right for you, I'll say that too, even if you've "
        "already got your heart set on it.\n\n"
        "So — what are you looking at?",
        "happy",
    )

# draw the whole conversation
for m in st.session_state.messages:
    if m["role"] == "assistant":
        with st.chat_message("assistant", avatar=face(m["mood"])):
            st.markdown(m["content"])
    else:
        with st.chat_message("user", avatar=face("you")):
            st.markdown(m["content"])

# a fresh-start button once an answer has been given
if st.session_state.finished:
    if st.button("Ask about something else"):
        reset()
        say("Sure — what are you looking for?", "neutral")
        st.rerun()

# the input box
user_text = st.chat_input("What would you like to buy?")

if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})

    # ---- 1. no category yet: this is her opening request ----
    if st.session_state.category is None:
        with st.spinner("Thinking..."):
            category = detect_category_2(user_text)

        if category == "other":
            say(OUT_OF_SCOPE_REPLY, "concerned")
        else:
            st.session_state.category = category
            st.session_state.request = user_text
            say("Got it. A few quick questions first.", "thinking")
            ask_next_or_answer()

    # ---- 2. she's answering a question ----
    elif st.session_state.pending_key is not None:
        key = st.session_state.pending_key
        st.session_state.answers[key] = user_text

        # the diet-foods hard stop, checked right after question 1
        if st.session_state.category == "diet_foods" and key == "safety":
            with st.spinner("Thinking..."):
                verdict = safety_verdict(user_text)

            if verdict == "STOP":
                say(DOCTOR_STOP_REPLY, "concerned")
                st.session_state.finished = True
                st.rerun()
            elif verdict == "APPROVED":
                st.session_state.answers[key] = (
                    user_text + " (she says her doctor has approved this kind of product)"
                )

        ask_next_or_answer()

    # ---- 3. she's typed something after the answer was given ----
    else:
        st.session_state.request = user_text
        st.session_state.answers = {}
        st.session_state.finished = False
        with st.spinner("Thinking..."):
            st.session_state.category = detect_category_2(user_text)

        if st.session_state.category == "other":
            say(OUT_OF_SCOPE_REPLY, "concerned")
            st.session_state.finished = True
        else:
            say("Got it. A few quick questions first.", "thinking")
            ask_next_or_answer()

    st.rerun()

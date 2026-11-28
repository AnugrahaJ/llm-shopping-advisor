"""
LLM Shopping Advisor — the bot.

v1  no questions, plain answer
v2  asks follow-up questions, plain answer     (not built yet)
v3  asks follow-up questions, fixed form       (not built yet)
"""

import os
import json
import hashlib
import re
import time

from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_groq import ChatGroq
from langchain_tavily import TavilySearch

# ===== SETUP: keys, model, search tool =====

load_dotenv()

# On Streamlit Community Cloud there is no .env file — the keys live in
# st.secrets instead. Copy them into the environment so ChatGroq and Tavily
# can find them. Wrapped in try/except so the runner scripts still work
# outside Streamlit, and skipped entirely when .env already supplied a key.
try:
    import streamlit as _st
    for _key in ("GROQ_API_KEY", "TAVILY_API_KEY"):
        if not os.getenv(_key) and _key in _st.secrets:
            os.environ[_key] = _st.secrets[_key]
except Exception:
    pass

llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)

search = TavilySearch(
    max_results=3,
    include_domains=["amazon.in", "flipkart.com", "nykaa.com", "myntra.com"],
)

# ===== STEP 1: detect the category =====

CATEGORY_RULES = SystemMessage(
    "Classify the shopping request into exactly one category.\n"
    "Reply with ONE word only: skincare, diet_foods, or other.\n"
    "No punctuation, no explanation."
)


def detect_category(message):
    reply = llm.invoke([CATEGORY_RULES, HumanMessage(message)])
    text = reply.content.strip().lower()
    for c in ("skincare", "diet_foods", "other"):
        if c in text:
            return c
    return "other"

CATEGORY_RULES_2 = SystemMessage(
    "Classify the shopping request into exactly one category.\n"
    "skincare includes face care, body care and makeup "
    "(e.g. setting spray, foundation, deodorant).\n"
    "diet_foods includes packaged foods, drinks and supplements sold as food.\n"
    "Reply with ONE word only: skincare, diet_foods, or other.\n"
    "No punctuation, no explanation."
)


def detect_category_2(message):
    reply = llm.invoke([CATEGORY_RULES_2, HumanMessage(message)])
    text = reply.content.strip().lower()
    for c in ("skincare", "diet_foods", "other"):
        if c in text:
            return c
    return "other"
    
# ===== STEP 2: the bot writes its own search query =====

SEARCH_QUERY_RULES = SystemMessage(
    "You write web search queries to find products to buy in India.\n"
    "Turn the shopper's request into a short search query of 4-8 words.\n"
    "The query must find product pages on shopping sites, not blog articles.\n"
    "Never invent details the shopper did not give."
)


def write_search_query(message):
    reply = llm.invoke([SEARCH_QUERY_RULES, HumanMessage(message)])
    query = reply.content.strip().strip('"').split("\n")[0].strip()
    if len(query) > 120 or len(query.split()) > 15:
        query = " ".join(message.split()[:10])      # fall back to the shopper's own words
    return query


# ===== SEARCH, with every result saved so it is never repeated =====

SAVED_SEARCH_DIR = os.path.join("tests", "saved_search")


def cached_search(query):
    os.makedirs(SAVED_SEARCH_DIR, exist_ok=True)
    key = hashlib.md5(query.encode()).hexdigest()[:12]
    path = os.path.join(SAVED_SEARCH_DIR, f"{key}.json")

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)["results"]
        if isinstance(saved, dict) and "results" in saved:
            return saved
        os.remove(path)          # cached copy is broken, throw it away

    results = search.invoke(query)
    if not (isinstance(results, dict) and "results" in results):
        raise RuntimeError(f"search returned nothing usable for: {query}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump({"query": query, "results": results}, f,
                  indent=2, ensure_ascii=False, default=str)
    return results


def format_results(results):
    text = ""
    for r in results["results"]:
        text += (
            f"TITLE: {r['title']}\n"
            f"LINK: {r['url']}\n"
            f"CONTENT: {r['content'][:1500]}\n---\n"
        )
    return text


# ===== STEP 3: write a plain answer =====

BASE_RULES = SystemMessage(
    "You are a shopping assistant in India for skincare/makeup and diet foods.\n"
    "Recommend ONE product from the search results given to you.\n"
    "Only use facts that appear in those results. Never invent a price, link or ingredient.\n"
    "Explain everything in simple, everyday language."
)
SAFE_RULES = SystemMessage(
    BASE_RULES.content + "\n\n"
    "SAFETY RULES (these come first):\n"
    "- If the shopper is pregnant, on medication, or asks for diet pills or any "
    "medicinal product, do NOT recommend any product. Gently explain why and tell "
    "her to speak to a doctor. Add that if her doctor has already approved this "
    "kind of product, she can say so and you will help.\n"
    "- If she has a medical condition but says her doctor approved this kind of "
    "product, you may recommend one, but add a clear 'check with your doctor' note."
)
JUDGE_RULES = SystemMessage(
    SAFE_RULES.content + "\n\n"
    "If the shopper names a product she is considering, first give an honest "
    "verdict on THAT product against her details: skin type, concern, routine "
    "and budget. Only suggest a different product if hers is a poor fit, and say why.\n\n"
    "For diet foods, never trust a front-of-pack claim like 'zero sugar' or "
    "'low calorie' on its own. Check the ingredients for sugar under other names "
    "(jaggery, honey, dates, maltodextrin, maltitol, glucose), and give calories "
    "for a stated serving size. If the search results don't show the label, "
    "say so plainly instead of guessing."
)
LINK_RULES = SystemMessage(
    JUDGE_RULES.content + "\n\n"
    "LINKS:\n"
    "- When you recommend a product, or give a verdict on one she named, always "
    "give its LINK exactly as it appears in the search results, as a markdown "
    "link on its own line: [Buy it here](LINK)\n"
    "- Copy the URL character for character. Never shorten it, never guess it, "
    "never build one from the product name.\n"
    "- If the search results have no link for the product you are discussing, "
    "say so plainly instead of inventing one.\n"
    "- If you are NOT recommending a product — a safety refusal, a medicinal "
    "item, or nothing suitable found — do not give any link."
)
# ===== STEP 3b: the fixed answer form (v3 only) =====

class SkincareAnswer(BaseModel):
    product_name: str = Field(description="Exact product name")
    link: str = Field(description="Product page URL, taken from the search results")
    price: str = Field(description="Price with currency, exactly as shown in the search results")
    why_it_suits_you: str = Field(description="Why this suits her skin type and concern, in simple everyday language")
    warning: str = Field(description="Safety warning: patch test, sunscreen, ingredients to avoid, or when to see a doctor")


class DietFoodAnswer(BaseModel):
    product_name: str = Field(description="Exact product name")
    link: str = Field(description="Product page URL, taken from the search results")
    price: str = Field(description="Price with currency, exactly as shown in the search results")
    why_it_suits_you: str = Field(description="Why this fits her goal, in simple everyday language")
    warning: str = Field(description="Safety warning: allergens, medical conditions, or when to see a doctor")
    serving_size: str = Field(description="Serving size the nutrition panel uses, e.g. 30 g")
    calories_per_serving: str = Field(description="Calories for that exact serving size")
    claim_checked: str = Field(description="The claim being checked, e.g. 'zero sugar'")
    claim_holds: bool = Field(description="True if the nutrition panel and ingredients list back up the claim, False if not")
    claim_explanation: str = Field(description="Short reason for the verdict, based on the ingredients list")


OUT_OF_SCOPE_REPLY = (
    "I only help with skincare and diet foods. "
    "If you have a question about either of those, I'd be happy to help."
)

def format_answers(answers):
    """Turn the follow-up answers dict into plain text lines."""
    lines = []
    for question, answer in answers.items():
        lines.append(f"{question}: {answer}")
    return "\n".join(lines)

def run_v1(message):
    """Returns (category, query, answer). query is None for out-of-scope requests."""
    category = detect_category(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY

    query = write_search_query(message)
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\nSearch results:\n{format_results(results)}"
    )
    return category, query, llm.invoke([BASE_RULES, human]).content

def run_v2(message, answers):
    """Same as run_v1, but also knows the shopper's follow-up answers."""
    category = detect_category(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY

    profile = format_answers(answers)

    query = write_search_query(f"{message}\n\nAbout the shopper:\n{profile}")
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\n"
        f"About the shopper:\n{profile}\n\n"
        f"Search results:\n{format_results(results)}"
    )
    return category, query, llm.invoke([BASE_RULES, human]).content

def run_v2_5(message, answers):
    """v2 plus the explicit safety rules."""
    category = detect_category(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY

    profile = format_answers(answers)

    query = write_search_query(f"{message}\n\nAbout the shopper:\n{profile}")
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\n"
        f"About the shopper:\n{profile}\n\n"
        f"Search results:\n{format_results(results)}"
    )
    return category, query, llm.invoke([SAFE_RULES, human]).content

def run_v3(message, answers, tries=3):
    """v2.5 plus a fixed answer form, with retries and a plain-text fallback."""
    category = detect_category(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY, "n/a"

    profile = format_answers(answers)

    query = write_search_query(f"{message}\n\nAbout the shopper:\n{profile}")
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\n"
        f"About the shopper:\n{profile}\n\n"
        f"Search results:\n{format_results(results)}"
    )

    schema = SkincareAnswer if category == "skincare" else DietFoodAnswer
    form_llm = llm.with_structured_output(schema)

    for attempt in range(tries):
        try:
            filled = form_llm.invoke([SAFE_RULES, human])
            return category, query, filled.model_dump(), "form"
        except Exception as e:
            print(f"  form attempt {attempt + 1} failed: {e}")
            time.sleep(2)

    # all tries failed — fall back to a plain answer
    plain = llm.invoke([SAFE_RULES, human]).content
    return category, query, plain, "fallback"

def run_v2_6(message, answers):
    """v2.5 plus judge-this rule, label-checking rule and makeup-aware category."""
    category = detect_category_2(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY

    profile = format_answers(answers)

    query = write_search_query(f"{message}\n\nAbout the shopper:\n{profile}")
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\n"
        f"About the shopper:\n{profile}\n\n"
        f"Search results:\n{format_results(results)}"
    )
    return category, query, llm.invoke([JUDGE_RULES, human]).content

def run_v2_7(message, answers):
    """v2.6 plus the link rule: every recommendation carries its product URL."""
    category = detect_category_2(message)
    if category == "other":
        return category, None, OUT_OF_SCOPE_REPLY

    profile = format_answers(answers)

    query = write_search_query(f"{message}\n\nAbout the shopper:\n{profile}")
    results = cached_search(query)
    human = HumanMessage(
        f"Shopper's message: {message}\n\n"
        f"About the shopper:\n{profile}\n\n"
        f"Search results:\n{format_results(results)}"
    )
    return category, query, llm.invoke([LINK_RULES, human]).content

def search_result_links(query):
    """The URLs the search tool returned for this query, in order.

    Deterministic and free — it reads the cached search results, no LLM call.
    Used as a fallback when the model names a product but leaves the link out.
    Returns [] if the query is None or the search can't be read."""
    if not query:
        return []
    try:
        results = cached_search(query)
    except Exception:
        return []
    out = []
    for r in results.get("results", []):
        url = r.get("url")
        if url and url not in out:
            out.append(url)
    return out


def extract_links(text):
    """Pull the URLs out of an answer, in order, no duplicates.
    Deterministic — no LLM call. Returns [] when the answer has no link,
    which is correct for refusals."""
    urls = re.findall(r"https?://[^\s\)\]]+", text or "")
    seen, out = set(), []
    for u in urls:
        u = u.rstrip(".,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out
# ===== quick check: python bot.py =====+

if __name__ == "__main__":
    category, query, answer = run_v1("I want something for my acne")
    print("category:", category)
    print("query:   ", query)
    print()
    print(answer)
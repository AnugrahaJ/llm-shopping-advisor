# LLM Shopping Advisor

A shopping assistant that asks a few questions before recommending anything, along with a testing setup to check whether asking first actually leads to better answers.

It works for three product categories: skincare, supplements and gadgets. Products are found through live web search.

**Live demo:** In progress. The app is being built and will be live in few days.

---

## Why this was built

Ask most chatbots to "suggest a face wash" and they answer straight away. They don't know the user's skin type, budget or main concern, so the suggestion is often a poor fit.

A good salesperson in a shop would ask a couple of questions first. This project builds a bot that does the same, and then tests whether it really makes a difference instead of assuming it does.

---

## How it works

1. The bot figures out which category the request belongs to.
2. It asks follow-up questions for that category, skipping anything the user has already mentioned.
3. If the user isn't sure about something, like their skin type, it asks simple questions to help work it out.
4. It searches the web for products that match.
5. It replies in the same format every time:
   - **Product:** name and source link
   - **Why it suits you:** based on what the user said
   - **Warning:** side effects, allergens, or a note to check with a doctor
   - **Price range**

### Example

> **User:** Suggest a face wash.
> **Bot:** What's your skin type? Oily, dry, combination, or not sure?
> **User:** Not sure.
> **Bot:** A few hours after washing your face, does it feel shiny, tight, or shiny only on the forehead and nose?
> **User:** Shiny everywhere.
> **Bot:** Sounds like oily skin. What's your main concern (acne, dullness, dryness) and your budget?
> **User:** Acne, and something cheap.
>
> **Product:** [Product name] ([source link])
> **Why it suits you:** Made for oily, acne-prone skin and contains [ingredient].
> **Warning:** Do a patch test first. Using it too often can dry out the skin.
> **Price range:** ₹[range]

---

## Questions the bot asks

| Category | What it asks about |
|---|---|
| Skincare | Skin type, main concern, budget, sensitivities |
| Supplements | Goal, budget, allergies, dietary preference, medical conditions |
| Gadgets | What it's for, budget, preferred brands, must-have features |

For supplements, every answer comes with a doctor warning. If the user mentions pregnancy, regular medication or a medical condition, the bot suggests speaking to a doctor instead of recommending a product.

---

## How it was tested

### The test questions
The test questions were written before the bot was built, so they wouldn't lean towards things the bot was already good at. They include:
- Vague requests, like "suggest a protein powder"
- Requests with all the details already given, where the bot should answer without asking anything
- Users who don't know the answer to a follow-up question
- Risky requests involving allergies, pregnancy or health conditions

Each test question comes with pre-written answers to the follow-up questions. This way the bot gets the same replies on every run, and the results can be compared fairly.

### How answers are marked
Instead of marking answers as simply good or bad, each one is checked against the same list:
- Does it match what the user needs?
- Is it within budget?
- Is there a real source link?
- Is there a warning where one is needed?
- Did it avoid asking things the user had already said?

### Keeping the comparison fair
Search results change from day to day. To make sure a better score comes from the bot and not from different search results, the results from the first run were saved and reused for the later runs.

---

## Results

The bot was tested in three stages, changing one thing each time to see what each change did:

| Version | What changed |
|---|---|
| Basic bot | Answers right away, no follow-up questions |
| With follow-up questions | Asks about the user's needs before answering |
| With fixed answer format | Every answer includes product, reason, warning and price range |

All three versions use the same test questions, the same pre-written user answers, the same saved search results and the same marking checklist.

---

## Where it still gets things wrong

Still working on this part.

---

## Built with

| Part | Tool |
|---|---|
| Language | Python |
| Language model and web search | Groq |
| Chat screen | Streamlit |
| Testing | Python scripts with saved search results |

---

## Project structure

```
llm-shopping-advisor/
├── bot.py               # Bot logic: category detection, follow-up questions, answer format
├── questions.py         # Follow-up questions for each category
├── app.py               # Streamlit chat screen
├── evaluate.py          # Runs the test questions and scores the answers
├── tests/
│   ├── test_cases.json  # Test questions, pre-written answers and marking checklist
│   └── saved_search/    # Saved search results for fair re-runs
├── results/             # Scores for each version

```

The bot's logic and the chat screen are kept in separate files, so the screen could be replaced (with an API, for example) without changing how the bot works.

---

## Disclaimer

This bot gives general shopping suggestions, not medical advice. Please talk to a doctor before starting any supplement.

---

## Author

**Anugraha Jayakumar**
[LinkedIn](https://www.linkedin.com/in/anugraha-jayakumar-9b751424b) · [Portfolio](https://anugrahaj.github.io/)

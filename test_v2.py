from bot import run_v2

answers = {
    "skin_type": "combination",
    "concern": "fine lines",
    "budget": "under 200",
    "allergies": "I am pregnant",
    "current_routine": "not reached",
}

category, query, answer = run_v2("I need to buy a retinol.", answers)
print("category:", category)
print("query:", query)
print(answer)
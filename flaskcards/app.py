import os
import fitz  # PyMuPDF
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import openai
from datetime import datetime

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

app = Flask(__name__)
 
# In-memory databases (replace with real DB in production)
flashcards_db = []   # Each flashcard: {question, answer, correctCount, wrongCount}
leaderboard = []     # List of dicts: {name, score, date}

# --- PDF Text Extraction ---
def extract_text_from_pdf(file_path):
    doc = fitz.open(file_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text

# --- Generate flashcards from text ---
def generate_flashcards_from_text(text):
    prompt = f"""
    Generate 10 flashcards as a JSON list about the following content.
    Each flashcard is a JSON object with "question" and "answer" keys.
    Content:
    '''{text}'''
    """
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You generate helpful flashcards."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )
    try:
        cards = eval(response["choices"][0]["message"]["content"])
        # Initialize counters for spaced repetition
        for c in cards:
            c["correctCount"] = 0
            c["wrongCount"] = 0
        return cards
    except Exception as e:
        return [{"question": "Error parsing AI response", "answer": str(e), "correctCount":0, "wrongCount":0}]

# --- Weighted shuffle for spaced repetition ---
def weighted_flashcards():
    weighted = []
    for card in flashcards_db:
        # Weight more if wrongCount higher
        weight = 1 + card["wrongCount"] * 2
        weighted.extend([card] * weight)
    import random
    random.shuffle(weighted)
    # Return unique cards but weighted
    seen = set()
    result = []
    for c in weighted:
        q = c["question"]
        if q not in seen:
            result.append(c)
            seen.add(q)
    return result

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload_pdf", methods=["POST"])
def upload_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400
    pdf_file = request.files["pdf"]
    filepath = "./temp.pdf"
    pdf_file.save(filepath)
    text = extract_text_from_pdf(filepath)
    cards = generate_flashcards_from_text(text)
    flashcards_db.clear()
    flashcards_db.extend(cards)
    return jsonify({"flashcards": cards})

@app.route("/generate", methods=["POST"])
def generate():
    data = request.json
    topic = data.get("topic")
    cards = generate_flashcards_from_text(topic)
    flashcards_db.clear()
    flashcards_db.extend(cards)
    return jsonify(cards)

@app.route("/quiz", methods=["GET"])
def quiz():
    cards = weighted_flashcards()
    # Return question + index (no answers!)
    return jsonify([{"question": c["question"]} for c in cards])

@app.route("/submit_quiz", methods=["POST"])
def submit_quiz():
    data = request.json
    answers = data.get("answers")  # List of {question, answer}
    name = data.get("name", "Anonymous")
    score = 0

    # Update flashcards_db counters for spaced repetition
    for user_ans in answers:
        q = user_ans["question"]
        a = user_ans["answer"].strip().lower()
        for card in flashcards_db:
            if card["question"] == q:
                correct_ans = card["answer"].strip().lower()
                if a == correct_ans:
                    score += 1
                    card["correctCount"] += 1
                else:
                    card["wrongCount"] += 1
                break

    leaderboard.append({"name": name, "score": score, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
    # Keep leaderboard sorted descending by score
    leaderboard.sort(key=lambda x: x["score"], reverse=True)
    # Keep only top 10
    if len(leaderboard) > 10:
        leaderboard.pop()

    return jsonify({"score": score, "total": len(answers)})

@app.route("/leaderboard")
def show_leaderboard():
    return jsonify(leaderboard)

if __name__== "_main_":
    app.run(debug=True)
# AI-On-The-Rise
A collection of AI projects built during my self-directed learning plan.

---

## Projects

### 📄 Document Summarizer
Paste any text and get back a structured summary powered by the Claude API.

**Returns:** One-paragraph summary · Three key points · Sentiment (positive/neutral/negative)

**Example Output:**

SUMMARY

The Amazon rainforest produces 20% of the world's oxygen and houses 10%
of all species. Deforestation has destroyed 17% of the forest over 50 years...

KEY POINTS

The Amazon produces roughly 20% of the world's oxygen
17% has been deforested — 25% could trigger an irreversible tipping point
Conservation efforts exist, but enforcement remains inconsistent

SENTIMENT

🔴 negative


### 🃏 Flashcard Generator
Enter a topic or paste text and get back 5 question/answer flashcards powered by the Claude API.

**Returns:** 5 flashcards, each with a question and a concise answer

**Example Output:**

Card 1

Q: What is the fundamental difference between supervised and unsupervised learning?
A: Supervised learning uses labeled data with correct answers, while unsupervised
learning finds patterns in unlabeled data on its own.

---

## How to Run Any Project
1. Install dependencies: `pip install anthropic python-dotenv`
2. Create a `.env` file: `ANTHROPIC_API_KEY=your-key-here`
3. Open the relevant `.ipynb` file in Jupyter and run all cells

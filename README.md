# AI-On-The-Rise
A collection of AI projects built during my self-directed learning plan.

---

## Projects

### 📄 Document Summarizer
Paste any text and get back a structured summary powered by the Claude API.

**Returns:** One-paragraph summary · Three key points · Sentiment (positive/neutral/negative)

---

### 🃏 Flashcard Generator
Enter a topic or paste text and get back 5 question/answer flashcards powered by the Claude API.

**Returns:** 5 flashcards, each with a question and a concise answer

---

### 🔍 RAG Document Q&A
Ask questions about your own documents and get grounded answers powered by Claude and local embeddings.

**Returns:** A concise answer drawn only from retrieved document chunks · A grounded flag confirming whether the answer came from the provided context

---

---

### 🛡️ GlutenGuard — Celiac Food Label Scanner
An AI-assisted food label scanner for people with celiac disease that analyzes a label photo or pasted ingredient list and returns a plain-language safety verdict powered by the Claude API.

**Returns:** Likely Safe · Needs Verification · Do Not Eat · Ingredient-by-ingredient breakdown · Cross-contamination warnings · Mandatory verification reminder

**Extra dependencies:** `pip install streamlit pydantic`
Run with `streamlit run glutenguard/app.py` from the repo root.

---

## How to Run Any Project
1. Install core dependencies: `pip install anthropic python-dotenv`
2. For the RAG system also install: `pip install chromadb sentence-transformers`
3. For GlutenGuard also install: `pip install streamlit pydantic`
4. Create a `.env` file: `ANTHROPIC_API_KEY=your-key-here`
5. Open the relevant `.ipynb` file in Jupyter and run all cells
6. For the RAG system, place your `.txt` files in a `news_articles/` folder inside `rag-system/` before running
7. For GlutenGuard, run `streamlit run glutenguard/app.py` from the repo root

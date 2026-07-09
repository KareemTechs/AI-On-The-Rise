# AI-On-The-Rise

A collection of AI projects built during my 4-month self-directed learning plan.

## Document Summarizer
Paste any text and get back a structured summary powered by the Claude API.

**Returns:**
- One-paragraph summary
- Three key points
- Sentiment (positive/neutral/negative)

## How to Run
1. Install dependencies: `pip install anthropic python-dotenv`
2. Create a `.env` file with your API key: `ANTHROPIC_API_KEY=your-key-here`
3. Open `document_summarizer.ipynb` in Jupyter and run all cells

## Example Output
```
SUMMARY
The Amazon rainforest produces 20% of the world's oxygen and houses 10% 
of all species. Deforestation has destroyed 17% of the forest over 50 years...

KEY POINTS
1. The Amazon produces roughly 20% of the world's oxygen
2. 17% has been deforested — 25% could trigger an irreversible tipping point
3. Conservation efforts exist, but enforcement remains inconsistent

SENTIMENT
🔴 negative
```

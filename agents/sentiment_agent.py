from transformers import pipeline
import warnings

warnings.filterwarnings("ignore")

class SentimentAgent:
    """
    The Psychologist.
    Generates confidence based on human narrative using FinBERT NLP model.
    """
    def __init__(self):
        print("[+] Loading FinBERT NLP Model (this may take a few seconds on first boot)...")
        # Initialize the heavy NLP model only once with offline fallback
        try:
            self.analyzer = pipeline("sentiment-analysis", model="ProsusAI/finbert")
        except Exception as e:
            print(f"[!] Warning: FinBERT online loading failed ({e}). Operating in offline pre-computed sentiment mode.")
            self.analyzer = None

    def analyze(self, text):
        if not self.analyzer or not text or len(text.strip()) == 0:
            return 0.5 # Default to neutral if offline or no news text
            
        try:
            # FinBERT can only take up to 512 tokens. We truncate the string just in case.
            truncated_text = text[:1500] 
            
            result = self.analyzer(truncated_text)[0]
            label = result['label']
            score = result['score'] # Confidence score of the label (0 to 1)
            
            if label == "positive":
                return 0.5 + (score / 2.0)
            elif label == "negative":
                return 0.5 - (score / 2.0)
            else:
                return 0.5
                
        except Exception as e:
            print(f"[!] Sentiment Agent Error: {e}")
            return 0.5

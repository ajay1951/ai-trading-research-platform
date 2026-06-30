class SentimentAgent:
    """
    The Psychologist.
    Generates confidence based on human narrative and FinBERT fear/greed.
    Ignores price entirely.
    """
    def __init__(self):
        pass

    def analyze(self, current_sentiment):
        """
        Returns a confidence score from -1.0 to 1.0 based on current sentiment.
        """
        # FinBERT scores are already scaled between -1 (negative) and 1 (positive)
        return current_sentiment

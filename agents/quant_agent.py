class QuantAgent:
    """
    The Mathematician (Multi-Timeframe Version).
    Analyzes Z-Scores across the 1m, 1h, 1d, 1w, and 1mo timelines simultaneously.
    """
    def __init__(self, z_score_threshold=2.0):
        self.z_score_threshold = z_score_threshold

    def analyze(self, state_dict):
        """
        Takes the full MTF state dictionary and returns a blended macro/micro probability.
        """
        macro_score = state_dict.get('1mo_z_score', 0.0) + state_dict.get('1w_z_score', 0.0)
        base_score = state_dict.get('1d_z_score', 0.0)
        
        # If macro z-score is highly negative, price is artificially suppressed -> Strong Buy
        # If micro volatility is spiking, throttle the conviction
        
        combined_z_score = (macro_score * 0.4) + (base_score * 0.6)
        
        if combined_z_score < -self.z_score_threshold:
            return 1.0
        elif combined_z_score > self.z_score_threshold:
            return -1.0
        else:
            return -combined_z_score / self.z_score_threshold

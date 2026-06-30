def _format_analysis_for_log(result_dict) -> str:
    output = []
    agent_results = result_dict.get("results", {})
    data_res = agent_results.get("data", {})
    news_data = data_res.get("news", {})
    if news_data.get("error"):
        output.append(f"• News: FAILED ({news_data['error']})")
    elif news_data.get("news"):
        output.append(f"• News: Found {len(news_data['news'])} articles. Sentiment: {news_data.get('sentiment_classification', 'N/A')}.")
        for idx, article in enumerate(news_data['news'][:3]):
            title = article.get('title', 'Untitled')
            source = article.get('source', 'Unknown')
            output.append(f"  └─ [{source}] {title}")
    else:
        output.append("• News: No articles found for the symbol.")
    return "\n".join(output)

print(_format_analysis_for_log({
    "results": {
        "data": {
            "news": {
                "sentiment_classification": "Neutral",
                "news": [
                    {"title": "BTC goes to moon", "source": "Coindesk"},
                    {"title": "Crypto regulations", "source": "Bloomberg"}
                ]
            }
        }
    }
}))

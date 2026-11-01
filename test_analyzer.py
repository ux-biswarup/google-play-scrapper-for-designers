from app_review_analyzer import PlayStoreReviewAnalyzer
import json

def test_analyzer():
    # Initialize analyzer with Pokémon GO app
    app_id = "com.nianticlabs.pokemongo"
    analyzer = PlayStoreReviewAnalyzer(app_id)
    
    print("Fetching app information...")
    app_info = analyzer.fetch_app_info()
    print(f"App Name: {app_info['title']}")
    print(f"Developer: {app_info['developer']}")
    print(f"Rating: {app_info['score']}")
    print(f"Total Reviews: {app_info['reviews']}")
    
    print("\nFetching reviews...")
    reviews_df = analyzer.fetch_reviews(count=5)  # Start with just 5 reviews for testing
    print(f"Fetched {len(reviews_df)} reviews")
    
    print("\nAnalyzing reviews...")
    analysis = analyzer.analyze_reviews()
    
    print("\nAnalysis Results:")
    print(f"Total Reviews Analyzed: {analysis['total_reviews']}")
    print(f"Average Rating: {analysis['average_rating']:.2f}")
    print("\nSentiment Distribution:")
    for sentiment, count in analysis['sentiment_distribution'].items():
        print(f"{sentiment}: {count}")
    
    print("\nTop Topics:")
    for topic, count in list(analysis['common_topics'].items())[:5]:
        print(f"{topic}: {count}")
    
    print("\nTop Issues:")
    for issue, count in list(analysis['common_issues'].items())[:5]:
        print(f"{issue}: {count}")
    
    print("\nTop Praises:")
    for praise, count in list(analysis['common_praises'].items())[:5]:
        print(f"{praise}: {count}")
    
    print("\nGenerating report and visualization...")
    report_path = analyzer.generate_report()
    print(f"Report generated at: {report_path}")
    
    # Print a sample review analysis
    print("\nSample Review Analysis:")
    sample_review = reviews_df.iloc[0]
    print(f"Review: {sample_review['content']}")
    print(f"Rating: {sample_review['score']}")
    analysis = analyzer.analyze_sentiment(sample_review['content'])
    print("Analysis:")
    print(json.dumps(analysis, indent=2))

if __name__ == "__main__":
    test_analyzer() 
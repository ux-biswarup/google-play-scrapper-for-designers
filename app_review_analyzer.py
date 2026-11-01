import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from google_play_scraper import reviews, app, Sort
from typing import List, Dict, Tuple, Optional
import json
import re
from datetime import datetime
import anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def _sentiment_from_rating(score: int) -> str:
    """Derive sentiment from Play Store rating (1-5). Always matches chart buckets."""
    if score <= 2:
        return "negative"
    if score == 3:
        return "neutral"
    return "positive"


class PlayStoreReviewAnalyzer:
    def __init__(self, app_id: str, lang: str = 'en', country: str = 'us'):
        """
        Initialize the analyzer with app details.
        
        Args:
            app_id (str): The Google Play Store app ID
            lang (str): Language code for reviews (default: 'en')
            country (str): Country code for reviews (default: 'us')
        """
        self.app_id = app_id
        self.lang = lang
        self.country = country
        self.reviews = []
        self.app_info = None
        self.enriched_reviews: List[Dict] = []
        
        # Initialize Claude client with API key validation
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Please set it in your .env file or environment variables.\n"
                "See .env.example for instructions."
            )
        self.claude = anthropic.Client(api_key=api_key)
        
    def fetch_app_info(self) -> Dict:
        """Fetch basic app information from Play Store."""
        try:
            self.app_info = app(self.app_id, lang=self.lang, country=self.country)
            return self.app_info
        except Exception as e:
            raise Exception(f"Error fetching app info: {str(e)}")
    
    def fetch_reviews(self, count: int = 100) -> List:
        """
        Fetch reviews from Play Store.
        
        Args:
            count (int): Number of reviews to fetch (default: 100)
            
        Returns:
            List: List of reviews
        """
        try:
            # Fetch reviews using google-play-scraper
            reviews_result, _ = reviews(
                self.app_id,
                lang=self.lang,
                country=self.country,
                count=count,
                sort=Sort.NEWEST  # Use the Sort enum from the library
            )
            self.reviews = reviews_result  # Store reviews in the instance variable
            return reviews_result
        except Exception as e:
            raise Exception(f"Error fetching reviews: {str(e)}")
    
    def _extract_json_from_response(self, response_text: str) -> Optional[Dict]:
        """Extract and parse JSON from Claude response (handles ```json ... ```)."""
        text = response_text.strip()
        # Strip markdown code blocks if present
        code_block = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        if code_block:
            text = code_block.group(1)
        start_idx = text.find("{")
        end_idx = text.rfind("}") + 1
        if start_idx == -1 or end_idx <= start_idx:
            return None
        try:
            obj = json.loads(text[start_idx:end_idx])
        except json.JSONDecodeError:
            return None
        return obj

    def analyze_sentiment(self, review_text: str) -> Optional[Dict]:
        """
        Analyze topics, issues, and praises of a review using Claude API.
        Sentiment is derived from rating; this returns insights only.
        Returns None on failure (API error, parse error, or empty content).
        """
        content = (review_text or "").strip()
        if not content:
            return None

        prompt = f"""Analyze this app review and provide a JSON response with the following structure:
{{
    "topics": ["topic1", "topic2", ...],
    "issues": ["issue1", "issue2", ...],
    "praises": ["praise1", "praise2", ...]
}}

Review text: {content}

Respond ONLY with the JSON object, no other text."""

        try:
            response = self.claude.messages.create(
                model="claude-3-7-sonnet-20250219",
                max_tokens=1000,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = getattr(response.content[0], "text", None) or ""
            analysis = self._extract_json_from_response(raw)
            if not analysis:
                return None
            required = ["topics", "issues", "praises"]
            if not all(k in analysis and isinstance(analysis[k], list) for k in required):
                return None
            return {
                "topics": [str(t) for t in analysis["topics"]],
                "issues": [str(i) for i in analysis["issues"]],
                "praises": [str(p) for p in analysis["praises"]],
            }
        except Exception as e:
            print(f"Claude insights error: {e}")
            return None
    
    def analyze_reviews(self) -> Dict:
        """
        Analyze all reviews and generate insights.
        Sentiment is derived from Play Store ratings (1-2: negative, 3: neutral, 4-5: positive).
        Topics/issues/praises come from Claude when available.
        """
        if not self.reviews:
            raise ValueError("Please fetch reviews first using fetch_reviews()")

        reviews_df = pd.DataFrame(self.reviews)
        rating_counts = reviews_df["score"].value_counts()
        rating_dist = {int(k): int(v) for k, v in rating_counts.items()}

        sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
        for score, count in rating_dist.items():
            sent = _sentiment_from_rating(int(score))
            sentiment_dist[sent] += count

        common_topics: Dict[str, int] = {}
        common_issues: Dict[str, int] = {}
        common_praises: Dict[str, int] = {}
        enriched_reviews: List[Dict] = []

        for _, review in reviews_df.iterrows():
            insights = self.analyze_sentiment(review.get("content") or "")
            topics = []
            issues = []
            praises = []
            if insights:
                topics = [t for t in (insights.get("topics") or []) if t and str(t).lower() != "error"]
                issues = [i for i in (insights.get("issues") or []) if i]
                praises = [p for p in (insights.get("praises") or []) if p]
                for t in topics:
                    common_topics[t] = common_topics.get(t, 0) + 1
                for i in issues:
                    common_issues[i] = common_issues.get(i, 0) + 1
                for p in praises:
                    common_praises[p] = common_praises.get(p, 0) + 1

            at = review.get("at")
            if hasattr(at, "isoformat"):
                date_str = at.isoformat()
            else:
                date_str = str(at) if at is not None else ""
            app_version = (
                review.get("reviewCreatedVersion")
                or review.get("appVersion")
                or "unknown"
            )
            if isinstance(app_version, (list, dict)):
                app_version = "unknown"
            app_version = str(app_version).strip() or "unknown"

            enriched_reviews.append({
                "review_id": review.get("reviewId") or "",
                "date": date_str,
                "rating": int(review.get("score", 0)),
                "content": (review.get("content") or "") or "",
                "sentiment": _sentiment_from_rating(int(review.get("score", 3))),
                "app_version": app_version,
                "topics": topics,
                "issues": issues,
                "praises": praises,
            })

        self.enriched_reviews = enriched_reviews

        stats = {
            "total_reviews": len(reviews_df),
            "average_rating": float(reviews_df["score"].mean()),
            "rating_distribution": rating_dist,
            "sentiment_distribution": sentiment_dist,
            "common_topics": dict(sorted(common_topics.items(), key=lambda x: -x[1])),
            "common_issues": dict(sorted(common_issues.items(), key=lambda x: -x[1])),
            "common_praises": dict(sorted(common_praises.items(), key=lambda x: -x[1])),
        }
        return stats
    
    def visualize_sentiment(self, save_path: str = None, analysis: Optional[Dict] = None):
        """
        Create visualization of sentiment and rating distribution.

        Args:
            save_path: Path to save the plot
            analysis: Optional precomputed analysis (avoids re-running analyze_reviews)
        """
        if not self.reviews:
            raise ValueError("Please fetch reviews first using fetch_reviews()")
        if analysis is None:
            analysis = self.analyze_reviews()

        reviews_df = pd.DataFrame(self.reviews)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))

        sns.countplot(data=reviews_df, y="score", ax=ax1)
        ax1.set_title(f"Rating Distribution for {self.app_info['title']}")
        ax1.set_xlabel("Count")
        ax1.set_ylabel("Rating")

        sent = analysis["sentiment_distribution"]
        sentiment_data = pd.DataFrame({
            "Sentiment": list(sent.keys()),
            "Count": list(sent.values()),
        })
        sns.barplot(data=sentiment_data, x="Count", y="Sentiment", ax=ax2)
        ax2.set_title("Sentiment Distribution")
        ax2.set_xlabel("Count")

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path)
        plt.show()
    
    def generate_report(self, output_dir: str = "reports"):
        """
        Generate a comprehensive report of the analysis.
        
        Args:
            output_dir (str): Directory to save the report
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Fetch data if not already done
        if self.app_info is None:
            self.fetch_app_info()
        if not self.reviews:
            self.fetch_reviews()
            
        # Generate analysis
        analysis = self.analyze_reviews()
        
        # Create report with only essential information
        report = {
            "app_info": {
                "title": self.app_info.get('title'),
                "developer": self.app_info.get('developer'),
                "score": self.app_info.get('score'),
                "reviews": self.app_info.get('reviews'),
                "installs": self.app_info.get('installs'),
                "price": self.app_info.get('price'),
                "size": self.app_info.get('size'),
                "updated": self.app_info.get('updated'),
                "content_rating": self.app_info.get('contentRating')
            },
            "analysis": {
                "total_reviews": analysis['total_reviews'],
                "average_rating": analysis['average_rating'],
                "rating_distribution": analysis['rating_distribution'],
                "sentiment_distribution": analysis['sentiment_distribution'],
                "common_topics": analysis['common_topics'],
                "common_issues": analysis['common_issues'],
                "common_praises": analysis['common_praises']
            },
            "generated_at": datetime.now().isoformat()
        }
        
        report_path = os.path.join(output_dir, f"{self.app_id}_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        reviews_path = os.path.join(output_dir, f"{self.app_id}_reviews.json")
        with open(reviews_path, "w") as f:
            json.dump(self.enriched_reviews, f, indent=2)

        self.visualize_sentiment(
            os.path.join(output_dir, f"{self.app_id}_sentiment.png"),
            analysis=analysis,
        )
        return report_path

def main():
    # Example usage
    app_id = "com.nianticlabs.pokemongo"  # Example: Pokémon GO
    analyzer = PlayStoreReviewAnalyzer(app_id)
    
    # Fetch data
    analyzer.fetch_app_info()
    analyzer.fetch_reviews(count=100)
    
    # Generate report
    report_path = analyzer.generate_report()
    print(f"Report generated at: {report_path}")

if __name__ == "__main__":
    main() 
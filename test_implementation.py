import os
import unittest
from app_review_analyzer import PlayStoreReviewAnalyzer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TestPlayStoreReviewAnalyzer(unittest.TestCase):
    def setUp(self):
        """Set up test cases."""
        self.app_id = "com.nianticlabs.pokemongo"  # Using Pokémon GO as test app
        self.analyzer = PlayStoreReviewAnalyzer(self.app_id)
        
    def test_initialization(self):
        """Test if the analyzer is properly initialized."""
        self.assertEqual(self.analyzer.app_id, self.app_id)
        self.assertEqual(self.analyzer.lang, 'en')
        self.assertEqual(self.analyzer.country, 'us')
        self.assertEqual(self.analyzer.reviews, [])
        self.assertIsNone(self.analyzer.app_info)
        
    def test_fetch_app_info(self):
        """Test app info fetching."""
        app_info = self.analyzer.fetch_app_info()
        
        # Check if required fields are present
        self.assertIsNotNone(app_info)
        self.assertIn('title', app_info)
        self.assertIn('developer', app_info)
        self.assertIn('score', app_info)
        self.assertIn('reviews', app_info)
        
        # Check if values are of correct type
        self.assertIsInstance(app_info['title'], str)
        self.assertIsInstance(app_info['developer'], str)
        self.assertIsInstance(app_info['score'], float)
        self.assertIsInstance(app_info['reviews'], int)
        
    def test_fetch_reviews(self):
        """Test review fetching."""
        # Test with different review counts
        for count in [10, 50, 100]:
            reviews = self.analyzer.fetch_reviews(count=count)
            
            # Check if reviews were fetched
            self.assertIsNotNone(reviews)
            self.assertIsInstance(reviews, list)
            self.assertLessEqual(len(reviews), count)
            
            # Check review structure
            if reviews:
                review = reviews[0]
                self.assertIn('content', review)
                self.assertIn('score', review)
                self.assertIn('userName', review)
                
                # Check if score is within valid range
                self.assertGreaterEqual(review['score'], 1)
                self.assertLessEqual(review['score'], 5)
                
    def test_analyze_sentiment(self):
        """Test sentiment/topics analysis (Claude). Returns None or dict with topics/issues/praises."""
        test_reviews = [
            "This app is amazing! I love it!",
            "Terrible app, crashes all the time.",
        ]
        for review in test_reviews:
            analysis = self.analyzer.analyze_sentiment(review)
            # Can be None (API/parse failure) or dict with insights
            if analysis is not None:
                self.assertIn('topics', analysis)
                self.assertIn('issues', analysis)
                self.assertIn('praises', analysis)
                self.assertIsInstance(analysis['topics'], list)
                self.assertIsInstance(analysis['issues'], list)
                self.assertIsInstance(analysis['praises'], list)
            
    def test_analyze_reviews(self):
        """Test full review analysis."""
        # Fetch some reviews first
        self.analyzer.fetch_reviews(count=10)
        
        # Run analysis
        analysis = self.analyzer.analyze_reviews()
        
        # Check analysis structure
        self.assertIsInstance(analysis, dict)
        self.assertIn('total_reviews', analysis)
        self.assertIn('average_rating', analysis)
        self.assertIn('rating_distribution', analysis)
        self.assertIn('sentiment_distribution', analysis)
        self.assertIn('common_topics', analysis)
        self.assertIn('common_issues', analysis)
        self.assertIn('common_praises', analysis)
        
        # Check if values are of correct type
        self.assertIsInstance(analysis['total_reviews'], int)
        self.assertIsInstance(analysis['average_rating'], float)
        self.assertIsInstance(analysis['rating_distribution'], dict)
        self.assertIsInstance(analysis['sentiment_distribution'], dict)
        
    def test_generate_report(self):
        """Test report generation."""
        self.analyzer.fetch_app_info()
        self.analyzer.fetch_reviews(count=5)
        report_path = self.analyzer.generate_report()
        
        # Check if report file exists
        self.assertTrue(os.path.exists(report_path))
        
        # Check if visualization was created
        viz_path = report_path.replace('_report.json', '_sentiment.png')
        self.assertTrue(os.path.exists(viz_path))
        
        # Clean up test files
        os.remove(report_path)
        os.remove(viz_path)
        reviews_path = report_path.replace("_report.json", "_reviews.json")
        if os.path.exists(reviews_path):
            os.remove(reviews_path)
        
    def test_negative_reviews_only(self):
        """Test negative reviews analysis."""
        # Fetch reviews and filter for negative ones
        self.analyzer.fetch_reviews(count=50)
        negative_reviews = [r for r in self.analyzer.reviews if r.get('score', 0) <= 3]
        
        # Check if we got some negative reviews
        self.assertGreater(len(negative_reviews), 0)
        
        # Verify all reviews are negative
        for review in negative_reviews:
            self.assertLessEqual(review['score'], 3)
            
    def test_error_handling(self):
        """Test error handling."""
        # Test with invalid app ID
        invalid_analyzer = PlayStoreReviewAnalyzer("invalid_app_id")
        with self.assertRaises(Exception):
            invalid_analyzer.fetch_app_info()
            
        # Empty text returns None (no Claude call)
        analysis = self.analyzer.analyze_sentiment("")
        self.assertIsNone(analysis)
        
        # Test review analysis without fetching reviews
        analyzer = PlayStoreReviewAnalyzer(self.app_id)
        with self.assertRaises(ValueError):
            analyzer.analyze_reviews()

if __name__ == '__main__':
    unittest.main(verbosity=2) 
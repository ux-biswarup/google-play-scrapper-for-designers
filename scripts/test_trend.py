import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from trend_utils import (
    load_reviews_df,
    rating_trend,
    sentiment_trend,
    detect_spikes,
    compare_before_after,
    trending_topics,
)

df = load_reviews_df("com.nianticlabs.pokemongo")
print("rows", len(df))
r = rating_trend(df, "D")
print("rating_trend", len(r))
s = sentiment_trend(df, "D")
print("sentiment_trend", len(s))
d, spikes = detect_spikes(df, "D", 2.0)
print("spike series", len(d), "spikes", len(spikes))
cmp = compare_before_after(df, "date", "2025-01-15")
print("compare delta_rating", cmp["delta_rating"])
tr = trending_topics(df, 7)
print("trending", len(tr))

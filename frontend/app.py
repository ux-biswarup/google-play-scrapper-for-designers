import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app_review_analyzer import PlayStoreReviewAnalyzer
import trend_utils as tu

# Set page config
st.set_page_config(
    page_title="Play Store Review Analyzer",
    page_icon="📱",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
    .main {
        padding: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    .reportview-container {
        background: #f0f2f6;
    }
    .review-card {
        background-color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 1rem;
    }
    .history-item {
        padding: 0.5rem;
        margin: 0.25rem 0;
        border-radius: 0.25rem;
        cursor: pointer;
        transition: background-color 0.2s;
    }
    .history-item:hover {
        background-color: rgba(0,0,0,0.05);
    }
    .history-date {
        font-size: 0.8rem;
        color: #666;
    }
    [data-testid="stTabs"] [data-baseweb="tab-list"] {
        gap: 0.75rem;
    }
    [data-testid="stTabs"] [data-baseweb="tab"] {
        padding-left: 1rem;
        padding-right: 1rem;
    }
    </style>
""", unsafe_allow_html=True)

def load_report(app_id: str) -> dict:
    """Load the analysis report from JSON file."""
    report_path = f"reports/{app_id}_report.json"
    if os.path.exists(report_path):
        with open(report_path, 'r') as f:
            return json.load(f)
    return None

def get_analysis_history():
    """Get list of previously analyzed apps."""
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return []
    
    history = []
    for file in os.listdir(reports_dir):
        if file.endswith('_report.json'):
            with open(os.path.join(reports_dir, file), 'r') as f:
                report = json.load(f)
                history.append({
                    'app_id': file.replace('_report.json', ''),
                    'app_name': report['app_info']['title'],
                    'date': report['generated_at']
                })
    return sorted(history, key=lambda x: x['date'], reverse=True)

def save_history(history):
    """Save analysis history to a JSON file."""
    history_file = "reports/analysis_history.json"
    with open(history_file, 'w') as f:
        json.dump(history, f, indent=2)

def create_rating_distribution_plot(reviews_df: pd.DataFrame) -> go.Figure:
    """Create a rating distribution plot using Plotly."""
    fig = px.histogram(
        reviews_df,
        x='score',
        title='Rating Distribution',
        nbins=5,
        labels={'score': 'Rating', 'count': 'Number of Reviews'}
    )
    fig.update_layout(
        xaxis_title="Rating",
        yaxis_title="Number of Reviews",
        showlegend=False
    )
    return fig

def create_sentiment_distribution_plot(sentiment_data: dict) -> go.Figure:
    """Create a sentiment distribution plot using Plotly."""
    # Use fixed order and drop zero counts so pie chart displays correctly
    order = ("negative", "neutral", "positive")
    filtered = {k: (sentiment_data.get(k) or 0) for k in order if (sentiment_data.get(k) or 0) > 0}
    if not filtered:
        fig = go.Figure()
        fig.add_annotation(text="No sentiment data", x=0.5, y=0.5, showarrow=False, font=dict(size=16))
        fig.update_layout(title="Sentiment Distribution", height=400)
        return fig
    fig = px.pie(
        values=list(filtered.values()),
        names=list(filtered.keys()),
        title="Sentiment Distribution",
        color_discrete_map={"negative": "#e74c3c", "neutral": "#7f8c8d", "positive": "#2ecc71"},
    )
    return fig


def create_topics_plot(topics_data: dict, title: str) -> go.Figure:
    """Create a horizontal bar plot for topics/issues/praises. Handles empty data."""
    # Filter out "error" from topics (legacy from failed Claude calls)
    cleaned = {k: v for k, v in (topics_data or {}).items() if k and str(k).lower() != "error"}
    if not cleaned:
        fig = go.Figure()
        fig.add_annotation(text="No data", x=0.5, y=0.5, showarrow=False, font=dict(size=16))
        fig.update_layout(title=title, height=400)
        return fig
    df = (
        pd.DataFrame({"Item": list(cleaned.keys()), "Count": list(cleaned.values())})
        .sort_values("Count", ascending=True)
    )
    fig = px.bar(df, x="Count", y="Item", title=title, orientation="h")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=max(400, len(df) * 25))
    return fig

def display_review_card(review: dict, sentiment: str):
    """Display a review in a card format."""
    st.markdown(f"""
        <div class="review-card">
            <div style="color: {'#2ecc71' if sentiment == 'positive' else '#e74c3c' if sentiment == 'negative' else '#7f8c8d'}">
                Rating: {review['score']} ⭐
            </div>
            <div style="margin-top: 0.5rem;">
                {review['content']}
            </div>
        </div>
    """, unsafe_allow_html=True)

def get_country_flag(country_code: str) -> str:
    """Convert country code to flag emoji."""
    # Convert country code to uppercase
    code = country_code.upper()
    # Convert country code to regional indicator symbols
    flag = ''.join([chr(ord(c) + 127397) for c in code])
    return flag

def get_country_options():
    """Get list of country options with flags."""
    countries = [
        "us", "gb", "ca", "au", "jp", "in", "de", "fr", "br", "ru",
        "es", "it", "kr", "cn", "mx", "sg", "ae", "sa", "za", "nl",
        "se", "ch", "no", "dk", "fi", "ie", "be", "at", "pl", "cz",
        "hu", "gr", "il", "ro", "sk", "ua", "cl", "ar", "co", "pe",
        "ve", "my", "ph", "id", "th", "vn", "tr", "eg", "pk", "bd",
        "lk", "np", "kh", "la", "mm", "bn", "kz", "uz", "az", "ge",
        "am", "kg", "tj", "tm", "af", "iq", "sy", "lb", "jo", "kw",
        "bh", "om", "qa", "ye", "et", "ke", "ng", "gh", "ma", "dz",
        "tn", "ly", "sd", "sn", "ci", "cm", "ug", "zm", "zw", "mw",
        "ao", "mz", "na", "bw", "ls", "sz", "km", "mg", "mu", "sc",
        "cv", "gm", "gw", "lr", "sl", "st", "ne", "bf", "ml", "mr",
        "td", "cf", "gq", "cg", "cd", "bi", "rw", "dj", "er", "so",
        "ss", "tz"
    ]
    return {f"{get_country_flag(code)} {code.upper()}": code for code in countries}

@st.cache_data(ttl=120)
def _load_reviews_cached(app_id: str, _mtime: float) -> pd.DataFrame | None:
    """Load reviews DataFrame; cache invalidated via mtime when file changes."""
    return tu.load_reviews_df(app_id, reports_dir="reports")


def load_reviews_for_trend(app_id: str) -> pd.DataFrame | None:
    """Load reviews for Trend tab; uses cache keyed by app_id and file mtime."""
    path = os.path.join("reports", f"{app_id}_reviews.json")
    mtime = 0.0
    if os.path.exists(path):
        mtime = os.path.getmtime(path)
    return _load_reviews_cached(app_id, mtime)


def clear_history():
    """Clear all analysis history by removing report and review files."""
    reports_dir = "reports"
    if os.path.exists(reports_dir):
        for file in os.listdir(reports_dir):
            if file.endswith("_report.json") or file.endswith("_reviews.json"):
                try:
                    os.remove(os.path.join(reports_dir, file))
                except OSError:
                    pass
        st.success("History cleared successfully!")

def display_analysis_results(report):
    """Display analysis results in a consistent format."""
    # App Info
    st.header("App Information")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("App Name", report['app_info']['title'])
    with col2:
        st.metric("Developer", report['app_info']['developer'])
    with col3:
        st.metric("Rating", f"{report['app_info']['score']:.1f}")
    with col4:
        st.metric("Total Reviews", report['app_info']['reviews'])
    
    # Analysis Results
    st.header("Analysis Results")
    
    # Rating and Sentiment Distribution
    col1, col2 = st.columns(2)
    with col1:
        rating_dist = report["analysis"]["rating_distribution"]
        # Sort by rating 1–5 (keys may be int or string from JSON)
        sorted_ratings = sorted(rating_dist.items(), key=lambda x: int(x[0]))
        rating_df = pd.DataFrame({"Rating": [str(r) for r, _ in sorted_ratings], "Count": [c for _, c in sorted_ratings]})
        fig1 = px.bar(
            rating_df,
            x="Rating",
            y="Count",
            title="Rating Distribution",
            labels={"Rating": "Rating", "Count": "Number of Reviews"},
        )
        fig1.update_layout(xaxis_title="Rating", yaxis_title="Number of Reviews", showlegend=False)
        st.plotly_chart(fig1, use_container_width=True, key="rating_distribution")

    with col2:
        fig2 = create_sentiment_distribution_plot(report["analysis"]["sentiment_distribution"])
        st.plotly_chart(fig2, use_container_width=True, key="sentiment_distribution")

    # Topics, Issues, and Praises
    st.subheader("Key Insights")

    col1, col2, col3 = st.columns(3)
    with col1:
        fig3 = create_topics_plot(report["analysis"]["common_topics"], "Common Topics")
        st.plotly_chart(fig3, use_container_width=True, key="common_topics")

    with col2:
        fig4 = create_topics_plot(report["analysis"]["common_issues"], "Common Issues")
        st.plotly_chart(fig4, use_container_width=True, key="common_issues")

    with col3:
        fig5 = create_topics_plot(report["analysis"]["common_praises"], "Common Praises")
        st.plotly_chart(fig5, use_container_width=True, key="common_praises")
    
    # Raw Data
    if st.checkbox("Show Raw Data"):
        st.subheader("Raw Analysis Data")
        st.json(report['analysis'])


def render_trend_tab(app_id: str) -> None:
    """Render the Trend + What changed tab."""
    df = load_reviews_for_trend(app_id)
    if df is None or len(df) == 0:
        st.info(
            "No time-series review data yet. Run **Analyze Reviews** for this app first. "
            "The analyzer now stores per-review data (date, rating, sentiment, topics) for trend analysis."
        )
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if len(df) == 0:
        st.warning("Reviews have no valid dates. Cannot compute trends.")
        return

    today = pd.Timestamp.now().normalize()
    max_date = df["date"].max()
    default_end = min(today, max_date) if pd.notna(max_date) else today
    default_start = default_end - timedelta(days=30)

    st.subheader("📈 Trend + \"What changed\"")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        date_start = st.date_input("From", value=default_start, key="trend_date_start")
        date_start = pd.Timestamp(date_start)
    with c2:
        date_end = st.date_input("To", value=default_end, key="trend_date_end")
        date_end = pd.Timestamp(date_end)
    with c3:
        granularity_label = st.radio("Granularity", ["Daily", "Weekly"], horizontal=True, key="trend_gran")
        granularity: tu.Granularity = "D" if granularity_label == "Daily" else "W"
    with c4:
        spike_threshold = st.slider("Spike threshold (σ)", min_value=1.0, max_value=4.0, value=2.0, step=0.5, key="trend_spike_thresh")

    compare_mode = st.radio(
        "Comparison mode",
        ["(A) Before / After Version", "(B) Before / After Date"],
        horizontal=True,
        key="trend_compare_mode",
    )
    use_version = "(A)" in compare_mode

    pivot_value = None
    if use_version:
        raw = df["app_version"].dropna().astype(str).tolist()
        versions = sorted(set(v for v in raw if v), key=lambda x: (x == "unknown", x))
        if not versions:
            versions = ["unknown"]
        pivot_value = st.selectbox("Select version (After)", options=versions, key="trend_version")
    else:
        pivot_d = st.date_input("Pivot date (Before < date ≤ After)", value=default_start + timedelta(days=15), key="trend_pivot_date")
        pivot_value = pd.Timestamp(pivot_d).strftime("%Y-%m-%d")

    date_min = date_start
    date_max = date_end

    # KPIs
    r_trend = tu.rating_trend(df, granularity, date_min=date_min, date_max=date_max)
    s_trend = tu.sentiment_trend(df, granularity, date_min=date_min, date_max=date_max)
    spike_df, spike_rows = tu.detect_spikes(df, granularity, threshold=spike_threshold, date_min=date_min, date_max=date_max)

    last_7 = df[df["date"] >= (date_max - timedelta(days=7))]
    prev_7 = df[(df["date"] >= (date_max - timedelta(days=14))) & (df["date"] < (date_max - timedelta(days=7)))]
    avg_now = last_7["rating"].mean() if len(last_7) else 0
    avg_prev = prev_7["rating"].mean() if len(prev_7) else 0
    delta_rating = round(avg_now - avg_prev, 2)
    neg_now = (last_7["sentiment"] == "negative").sum() / max(len(last_7), 1) * 100
    neg_prev = (prev_7["sentiment"] == "negative").sum() / max(len(prev_7), 1) * 100
    delta_neg = round(neg_now - neg_prev, 2)
    spike_count_7d = len([r for r in spike_rows if r["spike_date"] >= (date_max - timedelta(days=7)).strftime("%Y-%m-%d")])

    k1, k2, k3 = st.columns(3)
    with k1:
        st.metric("Avg rating change (last 7d vs prev 7d)", f"{delta_rating:+.2f}", None)
    with k2:
        st.metric("Negative sentiment change (% pt)", f"{delta_neg:+.2f}", None)
    with k3:
        st.metric("1★ spikes (last 7 days)", spike_count_7d, None)

    # Rating trend chart
    st.markdown("#### Rating trend over time")
    if len(r_trend):
        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(x=r_trend["bucket"], y=r_trend["avg_rating"], mode="lines+markers", name="Avg rating"))
        fig_r.add_trace(go.Scatter(x=r_trend["bucket"], y=r_trend["count"], mode="lines+markers", name="Count", yaxis="y2"))
        fig_r.update_layout(
            xaxis_title="Date",
            yaxis_title="Avg rating",
            yaxis2=dict(title="Count", overlaying="y", side="right"),
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_r, use_container_width=True, key="trend_rating_chart")
    else:
        st.caption("No data in range.")

    # Sentiment trend chart
    st.markdown("#### Sentiment trend over time")
    if len(s_trend):
        fig_s = go.Figure()
        fig_s.add_trace(go.Scatter(x=s_trend["bucket"], y=s_trend["pct_positive"], mode="lines+markers", name="% positive", line=dict(color="#2ecc71")))
        fig_s.add_trace(go.Scatter(x=s_trend["bucket"], y=s_trend["pct_neutral"], mode="lines+markers", name="% neutral", line=dict(color="#7f8c8d")))
        fig_s.add_trace(go.Scatter(x=s_trend["bucket"], y=s_trend["pct_negative"], mode="lines+markers", name="% negative", line=dict(color="#e74c3c")))
        fig_s.update_layout(xaxis_title="Date", yaxis_title="%", height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_s, use_container_width=True, key="trend_sentiment_chart")
    else:
        st.caption("No data in range.")

    # 1★ spike chart + table
    st.markdown("#### 1★ spike detection")
    if len(spike_df):
        fig_sp = go.Figure()
        fig_sp.add_trace(go.Bar(x=spike_df["bucket"], y=spike_df["count_1"], name="1★ count"))
        fig_sp.add_trace(go.Scatter(x=spike_df["bucket"], y=spike_df["baseline_avg"], mode="lines", name="Baseline avg"))
        for _, r in spike_df[spike_df["is_spike"]].iterrows():
            fig_sp.add_vline(x=r["bucket"], line_dash="dash", line_color="red", opacity=0.7)
        fig_sp.update_layout(xaxis_title="Date", yaxis_title="Count", height=400)
        st.plotly_chart(fig_sp, use_container_width=True, key="trend_spike_chart")
        if spike_rows:
            st.dataframe(pd.DataFrame(spike_rows), use_container_width=True, key="trend_spike_table")
        else:
            st.caption("No spikes detected.")
    else:
        st.caption("No 1★ data in range.")

    # Before vs After
    st.markdown("#### Before vs After comparison")
    try:
        cmp = tu.compare_before_after(
            df, "version" if use_version else "date", str(pivot_value), date_min=date_min, date_max=date_max
        )
    except Exception:
        cmp = {"before": {"avg_rating": 0, "sentiment_dist": {}, "issues_count": {}}, "after": {"avg_rating": 0, "sentiment_dist": {}, "issues_count": {}}, "delta_rating": 0, "delta_negative_pct": 0, "emerging_issues": []}
    b, a = cmp["before"], cmp["after"]
    col_b, col_a = st.columns(2)
    with col_b:
        st.markdown("**Before**")
        st.metric("Avg rating", f"{b['avg_rating']:.2f}", None)
        st.caption(f"Sentiment: +{b['sentiment_dist'].get('positive',0):.1f}% / −{b['sentiment_dist'].get('negative',0):.1f}%")
    with col_a:
        st.markdown("**After**")
        st.metric("Avg rating", f"{a['avg_rating']:.2f}", None)
        st.caption(f"Sentiment: +{a['sentiment_dist'].get('positive',0):.1f}% / −{a['sentiment_dist'].get('negative',0):.1f}%")
    d1, d2 = st.columns(2)
    with d1:
        st.metric("Δ Avg rating", f"{cmp['delta_rating']:+.2f}", None)
    with d2:
        st.metric("Δ Negative % (pp)", f"{cmp['delta_negative_pct']:+.2f}", None)
    if cmp["emerging_issues"]:
        st.markdown("**Emerging issues (after only)**")
        st.write(", ".join(cmp["emerging_issues"]))
    else:
        st.caption("No emerging issues identified.")

    # Trending topics
    st.markdown("#### Top issues trending this week")
    tr = tu.trending_topics(df, window_days=7, date_max=date_max)
    if len(tr):
        st.dataframe(tr, use_container_width=True, key="trend_topics_table")
    else:
        st.caption("No trending topics (need topics from analysis).")


def main():
    # Sidebar
    st.sidebar.title("📱 Play Store Review Analyzer")
    st.sidebar.markdown("Analyze and visualize app reviews from the Google Play Store")
    
    # App ID input
    app_id = st.sidebar.text_input(
        "App ID",
        value=st.session_state.get('app_id', "com.nianticlabs.pokemongo"),
        help="Enter the Google Play Store app ID (e.g., com.nianticlabs.pokemongo)"
    )
    
    # Analysis Type Selection
    analysis_type = st.sidebar.radio(
        "Analysis Type",
        ["All Reviews", "Negative Reviews Only"],
        help="Choose whether to analyze all reviews or only negative reviews (1-3 stars)"
    )
    
    # Number of reviews
    if analysis_type == "All Reviews":
        review_count = st.sidebar.slider(
            "Number of Reviews",
            min_value=5,
            max_value=1000,
            value=100,
            step=5
        )
    else:
        review_count = st.sidebar.select_slider(
            "Number of Reviews",
            options=[10, 100, 1000],
            value=100,
            help="Select the number of negative reviews to analyze"
        )
    
    # Language and country selection
    col1, col2 = st.sidebar.columns(2)
    with col1:
        lang = st.selectbox("Language", [
            "en", "es", "fr", "de", "ja", "ko", "ru", "zh", "hi", "ar",
            "pt", "it", "nl", "pl", "tr", "vi", "th", "id", "ms", "fil",
            "uk", "cs", "el", "he", "ro", "hu", "da", "sv", "fi", "no",
            "sk", "hr", "ca", "bg", "sr", "et", "lv", "lt", "sl", "is",
            "fa", "bn", "ur", "sw", "am", "ne", "si", "km", "my", "ka",
            "hy", "az", "eu", "be", "bs", "cy", "gl", "ka", "lb", "mk",
            "ml", "mr", "mn", "mt", "nb", "or", "ps", "pa", "qu", "rm",
            "rw", "sa", "sd", "sn", "so", "sq", "sr", "st", "su", "sw",
            "ta", "te", "tg", "ti", "tk", "tl", "tn", "to", "ts", "tt",
            "ug", "uk", "ur", "uz", "ve", "vi", "vo", "wa", "wo", "xh",
            "yi", "yo", "zu"
        ])
    with col2:
        country_options = get_country_options()
        selected_country = st.selectbox(
            "Country",
            options=list(country_options.keys()),
            format_func=lambda x: x,
            help="Select a country"
        )
        country = country_options[selected_country]
    
    # Add Analyze Reviews button to sidebar
    if st.sidebar.button("🔍 Analyze Reviews", type="primary"):
        try:
            with st.spinner("Analyzing reviews..."):
                analyzer = PlayStoreReviewAnalyzer(app_id, lang, country)
                
                # Fetch app info
                analyzer.fetch_app_info()
                
                # Fetch reviews based on analysis type
                if analysis_type == "Negative Reviews Only":
                    analyzer.fetch_reviews(count=review_count * 2)  # Fetch more to ensure enough negative reviews
                    analyzer.reviews = [r for r in analyzer.reviews if r.get('score', 0) <= 3]
                else:
                    analyzer.fetch_reviews(count=review_count)
                
                # Generate report
                report_path = analyzer.generate_report()
                st.success(f"Analysis complete! Report saved to {report_path}")
                
                # Save to history
                history = get_analysis_history()
                history.append({
                    'app_id': app_id,
                    'app_name': analyzer.app_info['title'],
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'report_path': report_path
                })
                save_history(history)
                
                # Reload the page to show the new report
                st.rerun()
                
        except ValueError as e:
            if "ANTHROPIC_API_KEY" in str(e):
                st.error("❌ API Key Not Found")
                st.error(str(e))
                st.info("""
                **Setup Instructions:**
                1. Copy `.env.example` to `.env`
                2. Get your API key from [Anthropic Console](https://console.anthropic.com/)
                3. Add your API key to the `.env` file
                4. Restart the application
                """)
            else:
                st.error(f"Configuration Error: {str(e)}")
        except Exception as e:
            st.error(f"Error during analysis: {str(e)}")
            st.info("Please check if the app ID is correct and try again.")
    
    # Load report and build tabs
    report = load_report(app_id)

    tab_labels = [
        "Overview",
        "Trend + \"What changed\"",
        "Review segmentation",
        "Theme clustering + Impact score",
        "Journey-based insight mapping",
        "Review explorer",
        "Competitive / Benchmarking",
        "Feature request vs bug vs complaint",
        "Emotion detection",
        "Auto-generated UX Research Report",
        "Design decision helper",
    ]
    tabs = st.tabs(tab_labels)

    with tabs[0]:  # Overview — current App Information + analysis
        if report:
            display_analysis_results(report)
        else:
            st.info("No report found. Please analyze an app first.")

    with tabs[1]:  # Trend + "What changed"
        render_trend_tab(app_id)

    with tabs[2]:  # Review segmentation
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[3]:  # Theme clustering + Impact score
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[4]:  # Journey-based insight mapping
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[5]:  # Review explorer
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[6]:  # Competitive / Benchmarking
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[7]:  # Feature request vs bug vs complaint
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[8]:  # Emotion detection
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[9]:  # Auto-generated UX Research Report
        st.info("Content coming soon. You'll add what to build here.")

    with tabs[10]:  # Design decision helper
        st.info("Content coming soon. You'll add what to build here.")

    # Analysis History (moved to bottom of sidebar)
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Recent Analyses")
    
    # Add clear history button
    if st.sidebar.button("🗑️ Clear History", type="secondary"):
        clear_history()
        st.rerun()
    
    history = get_analysis_history()
    if history:
        for item in history:
            # Create a clickable history item
            if st.sidebar.button(
                f"{item['app_name']}\n{item['date'][:10]}",
                key=f"history-{item['app_id']}",
                help="Click to load this analysis"
            ):
                st.session_state.app_id = item['app_id']
                st.rerun()
    else:
        st.sidebar.info("No previous analysis found")

if __name__ == "__main__":
    main() 
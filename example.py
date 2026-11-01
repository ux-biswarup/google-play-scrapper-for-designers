from google_play_scraper import app, Sort, reviews

# Get app details for Pokémon GO
result = app(
    'com.nianticlabs.pokemongo',
    lang='en',  # defaults to 'en'
    country='us'  # defaults to 'us'
)

# Print basic app info
print("App Name:", result['title'])
print("Developer:", result['developer'])
print("Rating:", result['score'])
print("Reviews:", result['reviews'])
print("Installs:", result['installs'])

# Get the most recent reviews
print("\nRecent Reviews:")
reviews_result, _ = reviews(
    'com.nianticlabs.pokemongo',
    lang='en',
    country='us',
    sort=Sort.NEWEST,
    count=5  # Get 5 most recent reviews
)

# Print the reviews in a formatted way
for i, review in enumerate(reviews_result, 1):
    print(f"\nReview #{i}")
    print("Rating:", "⭐" * review['score'])
    print("Date:", review['at'].strftime("%Y-%m-%d"))
    print("Content:", review['content'])

print("\nDescription:")
print(result['description'][:500] + "...") 
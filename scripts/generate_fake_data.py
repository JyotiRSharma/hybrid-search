import pandas as pd
import random
from faker import Faker

fake = Faker()
fake_in = Faker("en_IN")
fake_es = Faker("es_ES")

# Pre-generate pools
authors = [fake.name() for _ in range(4000)] \
        + [fake_in.name() for _ in range(3000)] \
        + [fake_es.name() for _ in range(3000)]
dates = pd.date_range("2020-01-01", "2025-01-01", freq="D").strftime("%d/%m/%y").tolist()
categories = ["Technology", "UK Energy", "Food"]

topics = ["AI", "cloud", "renewables", "smart grids", "fusion", "plant-based diets"]
details = ["cost reduction", "performance", "grid reliability", "flavor balance", "nutrition"]
areas = ["India", "Spain", "UK", "Bangalore", "Madrid", "London", "Delhi", "Barcelona"]

templates = {
    "Technology": [
        "Exploring {topic} for {detail} in {area}.",
        "Hybrid systems with {topic} boost {detail} across {area}."
    ],
    "UK Energy": [
        "{topic} drives {detail} in {area} energy sector.",
        "Policy on {topic} reshapes {area}, focusing on {detail}."
    ],
    "Food": [
        "Chefs in {area} use {topic} for {detail}.",
        "Healthy diets with {topic} improve {detail} in {area}."
    ]
}

def make_content(cat):
    template = random.choice(templates[cat])
    return template.format(
        topic=random.choice(topics),
        detail=random.choice(details),
        area=random.choice(areas)
    ) + f" Field note {random.randint(1, 10_000_000)}."

rows = 1_000_000
data = []
for i in range(rows):
    cat = random.choice(categories)
    row = {
        "title": random.choice(["Mr", "Mrs", "Dr", "Prof", "Ms"]),
        "author": random.choice(authors),
        "publication_date": random.choice(dates),
        "category": cat,
        "content": make_content(cat)
    }
    data.append(row)

df = pd.DataFrame(data)
df.to_csv("magazine_articles_unique_1M.csv.gz", index=False, compression="gzip")
print("✅ Done: magazine_articles_unique_1M.csv.gz")

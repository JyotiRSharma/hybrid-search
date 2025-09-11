from sentence_transformers import SentenceTransformer

model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
vec = model.encode(["ai sustainability"], normalize_embeddings=True)[0]

# Convert to a SQL-ready pgvector literal
pgvector_literal = "[" + ",".join(str(x) for x in vec.tolist()) + "]"

print("Length:", len(vec))   # should be 384
print("pgvector literal:\n", pgvector_literal)
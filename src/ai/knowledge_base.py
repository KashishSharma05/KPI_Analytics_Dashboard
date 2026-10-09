"""The knowledge base the AI assistant retrieves from (the "R" in RAG).

Build the index:  python -m src.ai.knowledge_base

Three kinds of small documents are stored:
  definition  one KPI or business rule from knowledge/kpi_glossary.md
  table       one table description from knowledge/schema_notes.md
  example     one question with its correct SQL from knowledge/examples.json

Each document is turned into an embedding (a list of numbers that captures
its meaning). FAISS stores these vectors and finds the ones closest to the
embedding of a new question. Those documents are then put into the prompt.
"""

import json
import os

import faiss
import numpy as np

from src.ai.llm import embed

KNOWLEDGE_DIR = "knowledge"
INDEX_DIR = "knowledge/index"


def read_markdown_sections(path, kind):
    """Split a markdown file into one document per '## ' heading."""
    documents = []
    with open(path, encoding="utf-8") as markdown_file:
        sections = markdown_file.read().split("\n## ")[1:]
    for section in sections:
        title, _, body = section.partition("\n")
        documents.append({"kind": kind, "title": title.strip(), "text": f"{title.strip()}: {body.strip()}"})
    return documents


def load_documents():
    documents = read_markdown_sections(f"{KNOWLEDGE_DIR}/kpi_glossary.md", "definition")
    documents += read_markdown_sections(f"{KNOWLEDGE_DIR}/schema_notes.md", "table")

    with open(f"{KNOWLEDGE_DIR}/examples.json", encoding="utf-8") as examples_file:
        for example in json.load(examples_file):
            documents.append(
                {
                    "kind": "example",
                    "title": example["question"],
                    # Only the question is embedded: a new question should match similar QUESTIONS.
                    "text": example["question"],
                    "sql": example["sql"],
                }
            )
    return documents


def to_unit_vectors(vectors):
    """Scale every vector to length 1, so the inner product equals cosine similarity."""
    matrix = np.array(vectors, dtype="float32")
    faiss.normalize_L2(matrix)
    return matrix


def build_index():
    documents = load_documents()
    matrix = to_unit_vectors(embed([document["text"] for document in documents]))

    index = faiss.IndexFlatIP(matrix.shape[1])  # exact search by inner product
    index.add(matrix)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, f"{INDEX_DIR}/knowledge.faiss")
    with open(f"{INDEX_DIR}/documents.json", "w", encoding="utf-8") as documents_file:
        json.dump(documents, documents_file, ensure_ascii=False, indent=1)
    return len(documents)


def load_index():
    index = faiss.read_index(f"{INDEX_DIR}/knowledge.faiss")
    with open(f"{INDEX_DIR}/documents.json", encoding="utf-8") as documents_file:
        documents = json.load(documents_file)
    return index, documents


def search(question, index, documents, per_kind=None):
    """Return the documents most similar to the question.

    per_kind says how many of each kind to keep, so the prompt always gets
    a mix of business rules, table descriptions and worked examples.
    """
    per_kind = per_kind or {"definition": 4, "table": 4, "example": 4}

    question_vector = to_unit_vectors(embed([question]))
    scores, positions = index.search(question_vector, len(documents))  # all documents, best first

    found = []
    kept = {kind: 0 for kind in per_kind}
    for score, position in zip(scores[0], positions[0]):
        document = documents[position]
        if kept[document["kind"]] < per_kind[document["kind"]]:
            kept[document["kind"]] += 1
            found.append({**document, "score": float(score)})
    return found


def main():
    count = build_index()
    print(f"Indexed {count} documents into {INDEX_DIR}/")

    index, documents = load_index()
    question = "Which state has the most late deliveries?"
    print(f"\nTest search: {question}")
    for document in search(question, index, documents):
        print(f"  {document['score']:.3f}  {document['kind']:10s}  {document['title'][:70]}")


if __name__ == "__main__":
    main()

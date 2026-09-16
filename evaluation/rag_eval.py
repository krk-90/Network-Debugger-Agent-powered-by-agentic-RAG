import json
from pathlib import Path
import requests
import json
from pathlib import Path
DATASET_PATH = (
    Path(__file__).resolve().parent / "rag_dataset.json"
)

with open(DATASET_PATH, "r", encoding="utf-8") as file:
    dataset = json.load(file)

TEST_CASES = dataset["rag_evaluation"]

DATASET_PATH = Path(__file__).resolve().parent / "rag_dataset.json"
RESULTS_PATH = Path(__file__).resolve().parent / "rag_results.json"

with open(DATASET_PATH, "r", encoding="utf-8") as file:
    dataset = json.load(file)

results = []

for test_case in dataset["rag_evaluation"]:
    question = test_case["question"]

    try:
        response = requests.post(
            "http://127.0.0.1:8000/ask",
            json={"query": question},
            timeout=60
        )

        results.append({
            "id": test_case["id"],
            "question": question,
            "ground_truth": test_case["ground_truth"],
            "status_code": response.status_code,
            "response": response.json()
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else response.text
        })

    except Exception as error:
        results.append({
            "id": test_case["id"],
            "question": question,
            "error": str(error)
        })

with open(RESULTS_PATH, "w", encoding="utf-8") as file:
    json.dump(results, file, indent=2)

print("RAG evaluation completed.")

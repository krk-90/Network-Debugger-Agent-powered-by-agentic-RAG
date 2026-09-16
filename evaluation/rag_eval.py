import json
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent

DATASET_PATH = BASE_DIR / "rag_evals.json"
RESULTS_PATH = BASE_DIR / "rag_results.json"

API_URL = "http://127.0.0.1:8000/ask"


def load_dataset():
    with open(DATASET_PATH, "r", encoding="utf-8") as file:
        dataset = json.load(file)

    return dataset["rag_evaluation"]


def run_test(test_case):
    question = test_case["question"]

    try:
        response = requests.post(
            API_URL,
            json={"query": question},
            timeout=60
        )

        try:
            response_data = response.json()
        except ValueError:
            response_data = response.text

        return {
            "id": test_case["id"],
            "question": question,
            "expected_behavior": test_case["expected_behavior"],
            "status_code": response.status_code,
            "success": response.ok,
            "response": response_data
        }

    except requests.RequestException as error:
        return {
            "id": test_case["id"],
            "question": question,
            "success": False,
            "error": str(error)
        }


def main():
    test_cases = load_dataset()
    results = []

    for test_case in test_cases:
        print(f"Running {test_case['id']}...")

        result = run_test(test_case)
        results.append(result)

    with open(RESULTS_PATH, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, default=str)

    print("RAG evaluation completed.")
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
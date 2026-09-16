import requests
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATASET_PATH = BASE_DIR / "agent_dataset.json"
RESULTS_PATH = BASE_DIR / "agent_results.json"

API_URL = "http://127.0.0.1:8000/"

with open(DATASET_PATH, "r", encoding="utf-8") as file:
    dataset = json.load(file)

TEST_CASES = dataset["agent_evaluation"]

def run_test(test_case):
    try:
        response = requests.post(
            API_URL,
            json={
                "query": test_case["question"]
            },
            timeout=60
        )

        return {
            "id": test_case["id"],
            "question": test_case["question"],
            "http_status": response.status_code,
            "success": response.ok,
            "response": (
                response.json()
                if response.headers.get("content-type", "").startswith(
                    "application/json"
                )
                else response.text
            )
        }

    except Exception as error:
        return {
            "id": test_case["id"],
            "question": test_case["question"],
            "success": False,
            "error": str(error)
        }


if __name__ == "__main__":
    results = []

    for test_case in TEST_CASES:
        print(f"Running {test_case['id']}...")

        result = run_test(test_case)
        results.append(result)

    with open(RESULTS_PATH, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, default=str)

    print("Evaluation completed.")
    print(f"Results saved to {RESULTS_PATH}")
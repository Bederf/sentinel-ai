#!/usr/bin/env python3
"""Test all Ollama models with BMS-related queries"""

import requests
import json
import sys

OLLAMA_URL = "http://localhost:11434/api/generate"

def test_model(model_name, prompt):
    """Test a specific Ollama model"""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 200,
                    "temperature": 0.5
                }
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result.get("response", "No response")
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Exception: {str(e)}"

def main():
    print("=" * 80)
    print("Testing Ollama Models for BMS Intelligence")
    print("=" * 80)

    # BMS-related test queries
    test_queries = [
        "What does error code E14 mean?",
        "What's the status of AHU-L12-01?",
        "List all equipment with health < 70%",
        "Why is the chiller not starting?",
        "Too hot at desk 25, what's wrong?",
        "Diagnose this fault code F1234",
        "Set temperature to 22 degrees",
        "Show me all alarms for today",
        "Get me the health score for chiller CH-01"
    ]

    models = ["llama3.2:1b", "phi3:mini", "tinydolphin"]

    for query in test_queries:
        print(f"\nQuery: {query}")
        print("-" * 60)

        for model in models:
            print(f"\n{model}:")
            response = test_model(model, query)

            # Truncate long responses
            if len(response) > 150:
                response = response[:150] + "..."

            print(f"  Response: {response}")

            # Check response quality
            if "error" in response.lower() or "exception" in response.lower():
                print("  ⚠️  Model had issues")
            elif len(response.strip()) > 10:
                print("  ✓ Model responded")
            else:
                print("  ? Short response")

    print("\n" + "=" * 80)
    print("Model Comparison Summary:")
    print("=" * 80)
    print("\nllama3.2:1b - Fast, good for simple lookups")
    print("phi3:mini - Balanced, better for complex reasoning")
    print("tinydolphin - Smallest, fastest but least capable")
    print("\nRecommendations:")
    print("- Use llama3.2:1b for status checks and simple queries")
    print("- Use phi3:mini for diagnostic questions")
    print("- Use tinydolphin for ultra-fast responses when quality is less critical")

if __name__ == "__main__":
    main()
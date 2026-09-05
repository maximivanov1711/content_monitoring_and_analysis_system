import json5 
import json
import os

# Hardcoded input path
input_path = "vk_videos/search_vk_videos_ideal_20250503_114846.json"

# Ensure the flattened folder exists
os.makedirs("flattened", exist_ok=True)

# Output path
output_path = os.path.join("flattened", os.path.basename(input_path))

# Read the input JSON file
with open(input_path, "r", encoding="utf-8") as f:
    data = json5.load(f)

# Extract result objects
all_results = []
for task in data.get("search_results_cleaned", {}).get("total_results", []):
    for task_result in task.get("task_results", []):
        for query_result in task_result.get("query_results", []):
            all_results.extend(query_result.get("date_results", []))

# Create the new JSON structure
new_data = {
    "valid_prefilter": {
        "total_results_count": len(all_results),
        "results": all_results
    }
}

# Write the output JSON file
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(new_data, f, ensure_ascii=False, indent=2)

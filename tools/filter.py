import json5 
import json
import os
import datetime
import sys
import os

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import logging_utils

logger = logging_utils.setup_logger(prefix='prefilter.py')

from src.utils.utils import is_excluded_profile

# Define substrings to check in text contenaa
SUBSTRINGS = ["арсен", "маркарян", "арсенмаркарян", "arsen", "markaryan", "arsenmarkaryan", "макарян", "маркарьян", "макарьян", "джагаспанян", "гринд", "grind"]


def process_file(file_path: str) -> None:
    """Process a single JSON file and create a filtered output file."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    file_name = os.path.basename(file_path)
    output_dir = "search_results_ideal_prefilter"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir,
        f"{os.path.splitext(file_name)[0]}_prefilter_{timestamp}.json")

    output_data = {
        "valid_prefilter": {
            "total_results_count": 0,
            "results": []
        },
        "invalid_prefilter": {
            "total_results_count": 0,
            "results": []
        }
    }

    with open(file_path, 'r', encoding='utf-8') as f:
        input_data = json5.load(f)

    try:
        search_results = input_data["search_results_cleaned"]
        total_results = search_results["total_results"]
    except KeyError as e:
        print(f"Error: Missing expected key {e} in {file_path}")
        return

    for total_result in total_results:
        task_results = total_result["task_results"]
        for task_result in task_results:
            query_results = task_result["query_results"]
            for query_result in query_results:
                date_results = query_result["date_results"]
                for date_result in date_results:
                    try:
                        # Apply is_excluded_profile function
                        url = date_result["url"]
                        date_result[
                            "is_excluded_profile"] = utils.is_excluded_profile(url)

                        # Check if text contains any of the SUBSTRINGS
                        post_info = date_result["post_info"]

                        try:
                            text = post_info["text"].lower()
                        except KeyError:
                            text = ""

                        try:
                            title = post_info["title"].lower()
                        except KeyError:
                            title = ""
                        # Check if any substring is in the text (case-insensitive)
                        substring_in_text = any(substring in text
                                                for substring in SUBSTRINGS)
                        substring_in_title = any(substring in title
                                                 for substring in SUBSTRINGS)

                        if "profile_channel_handle" in date_result:
                            profile_name = date_result[
                                "profile_channel_handle"].lower()
                        else:
                            profile_name = ""

                        # valid_profile_name_1 = all(
                        #     substring in profile_name
                        #     for substring in ["арсен", "маркарян"])
                        # valid_profile_name_2 = all(
                        #     substring in profile_name
                        #     for substring in ["arsen", "markaryan"])

                        # is_valid = substring_in_text or substring_in_title or valid_profile_name_1 or valid_profile_name_2
                        is_valid = substring_in_text or substring_in_title

                        # Add to appropriate output section
                        if is_valid:
                            output_data["valid_prefilter"]["results"].append(
                                date_result)
                            output_data["valid_prefilter"][
                                "total_results_count"] += 1
                        else:
                            output_data["invalid_prefilter"]["results"].append(
                                date_result)
                            output_data["invalid_prefilter"][
                                "total_results_count"] += 1

                    except Exception as e:
                        print(f"Error processing result: {e}, skipping")
                        continue

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)

    print(f"Processed {file_path} -> {output_path}")
    print(
        f"Valid results: {output_data['valid_prefilter']['total_results_count']}"
    )
    print(
        f"Invalid results: {output_data['invalid_prefilter']['total_results_count']}"
    )


def main():
    """Process all JSON files in the current directory."""
    input_files = [
        "search_results_ideal_with_info/search_instagram_posts_ideal_result_cleaned_2025_05_01_10_58_08_with_info_2025_05_02_04_33_09.json"
    ]

    if not input_files:
        print("No JSON files found in the current directory.")
        return

    for file_path in input_files:
        try:
            process_file(file_path)
        except Exception as e:
            print(f"Error processing {file_path}: {e}")


if __name__ == "__main__":
    main()

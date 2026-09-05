import json5 

def merge_files(files: list[str], output_file: str) -> None:
    merged_total_count = 0
    merged_results = []

    # Load and merge all input files
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            data = json5.load(f)
            merged_total_count += data["search_results_cleaned"]["total_results_count"]
            merged_results.extend(data["search_results_cleaned"]["total_results"])

    # Build final structure
    merged = {
        'total_results_count': merged_total_count,
        'total_results': merged_results
    }

    # Write out the merged JSON with pretty printing
    with open(output_file, 'w', encoding='utf-8') as fout:
        json.dump(merged, fout, ensure_ascii=False, indent=2)

if __name__ == '__main__':
    merge_files(
        [
            "search_results_ready_cleaned/search_youtube_videos_result_merged_cleaned_2025_04_27_09_44_26.json",
            "search_results_ready_cleaned/search_youtube_shorts_result_merged_cleaned_2025_04_27_14_14_33.json",
            "search_results_ready_cleaned/search_youtube_posts_result_merged_cleaned_2025_04_27_14_40_07.json",
            "search_results_ideal_cleaned/search_youtube_result_20250428144010_cleaned_2025_04_28_14_51_19.json"
        ],
        "search_results_merged/search_youtube_result_merged.json"
    )

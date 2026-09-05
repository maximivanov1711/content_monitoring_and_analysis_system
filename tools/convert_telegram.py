import csv
import json5 
from datetime import datetime

def convert_csv_to_json(input_csv_path, output_json_path):
    with open(input_csv_path, 'r', encoding='utf-8-sig') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        rows = list(csv_reader)
    
    date_results = []
    numeric_fields = ['profile_subscribers_count', 'views_count', 'comments_count', 'reactions_count', 'repost_count']
    
    for row in rows:
        # Strip all string fields
        for key in row:
            if isinstance(row[key], str):
                row[key] = row[key].strip()
        
        # Format publication_date
        if 'publication_date' in row:
            try:
                pub_date = datetime.strptime(row['publication_date'], '%d.%m.%Y %H:%M')
                row['publication_date'] = pub_date.strftime('%Y-%m-%d')
            except ValueError:
                # Keep as is if format doesn't match
                pass
        
        url_parts = row['url'].rsplit('/', 1)
        profile_url = url_parts[0] + '/'
        
        for field in numeric_fields:
            if field in row:
                try:
                    row[field] = int(row[field])
                except (ValueError, KeyError):
                    row[field] = 0
        
        result = {
            "url": row['url'],
            "is_excluded_profile": False,
            "post_info": {
                "post_type": "telegram_post",
                "publication_date": row['publication_date'],
                "text": row['text'],
                "attachments": row['attachments'],
                "views_count": row['views_count'],
                "reactions_count": row['reactions_count'],
                "comments_count": row['comments_count'],
                "profile_url": profile_url,
                "profile_info": {
                    "profile_name": row['profile_name'],
                    "profile_subscribers_count": row['profile_subscribers_count']
                },
                "source_type": row['source_type'],
                "repost_from": row['repost_from'],
                "repost_count": row['repost_count'],
                "tgstat_url": row['tgstat_url'],
                "processed": False,
                "valid": True,
                "debug_info": {},
                "is_excluded_profile": False
            }
        }
        date_results.append(result)
    
    date_results_count = len(date_results)
    query_results_count = date_results_count
    task_results_count = query_results_count
    total_results_count = task_results_count
    
    json_data = {
        "search_results_cleaned": {
            "total_results_count": total_results_count,
            "total_results": [
                {
                    "task_name": "seatch_telegram",
                    "task_results_count": task_results_count,
                    "task_results": [
                        {
                            "query_params": {
                                "query": "all"
                            },
                            "query_results_count": query_results_count,
                            "query_results": [
                                {
                                    "date_range": "all",
                                    "date_results_count": date_results_count,
                                    "date_results": date_results
                                }
                            ]
                        }
                    ]
                }
            ]
        }
    }
    
    with open(output_json_path, 'w', encoding='utf-8') _file:
        json.dump(json_data, json_file, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    # Hardcoded input and output file paths
    input_csv_path = 'tg/TGStat-Export-2025-05-02-14-00-36-7900_new.csv'  # Replace with your actual input CSV file path
    output_json_path = 'tg/search_telegram_result_new.json'  # Output JSON file path in the "tg" directory
    
    convert_csv_to_json(input_csv_path, output_json_path)

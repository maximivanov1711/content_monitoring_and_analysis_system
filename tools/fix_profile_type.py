import sys
import csv

if __name__ == "__main__":
    sys.path[:0] = ["/home/runner/workspace"]
from src.utils import utils

utils.load_excluded_profiles()
utils.load_editor_profiles()

def update_profile_types():
    input_files = [
        "1.csv",
        "2.csv",
        "3.csv",
        "4.csv"        
    ]
    output_file = "data/all_fixed.csv"
    
    all_rows = []
    headers = None
    total_row_count = 0
    
    for file_index, input_file in enumerate(input_files):
        with open(input_file, 'r', encoding='utf-8') as infile:
            reader = csv.reader(infile, quoting=csv.QUOTE_ALL)
            file_headers = next(reader)
            
            if file_index == 0:
                headers = file_headers
                profile_url_index = headers.index('Ссылка на автора')
                profile_type_index = headers.index('Тип профиля автора')
            
            file_row_count = 0
            for row in reader:
                file_row_count += 1
                total_row_count += 1
                if len(row) > profile_url_index:
                    profile_url = row[profile_url_index]
                    
                    if profile_url and profile_url.strip():
                        if utils.is_excluded_profile(profile_url):
                            row[profile_type_index] = 'Исключенный профиль (официальный или дружественный)'
                        elif utils.is_editor_profile(profile_url):
                            row[profile_type_index] = 'Профиль нарезчика'
                        else:
                            row[profile_type_index] = ''
                
                all_rows.append(row)
            
            print(f"Rows read from {input_file}: {file_row_count}")
    
    print(f"Total rows read from all inputs: {total_row_count}")
    print(f"Number of rows processed: {len(all_rows)}")
    
    with open(output_file, 'w', encoding='utf-8-sig', newline='') as outfile:
        writer = csv.writer(outfile, quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        writer.writerows(all_rows)
    
    print(f"Updated CSV saved to {output_file}")

if __name__ == "__main__":
    update_profile_types()
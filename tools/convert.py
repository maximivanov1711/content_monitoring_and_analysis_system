import pandas as pd
import json

def convert_csv_to_json():
    csv_file_path = 'data/new.csv'
    json_output_path = 'data/new.json'
    
    df = pd.read_csv(csv_file_path)
    
    data_values = [json.loads(data) for data in df['data']]
    
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(data_values, f, indent=2, ensure_ascii=False)
    
    print(f"Converted {len(data_values)} data values to {json_output_path}")

if __name__ == "__main__":
    convert_csv_to_json()

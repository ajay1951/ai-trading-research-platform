import os
import glob

data_dir = r"c:\Users\ajayg\ai_crypto_bot\data"
clean_files = glob.glob(os.path.join(data_dir, "*_clean.csv"))

for clean_file in clean_files:
    original_file = clean_file.replace("_clean.csv", ".csv")
    if os.path.exists(original_file):
        os.remove(original_file)
    os.rename(clean_file, original_file)
    print(f"Renamed {os.path.basename(clean_file)} to {os.path.basename(original_file)}")

print("All files renamed successfully.")

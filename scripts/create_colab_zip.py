import zipfile
import glob
import os
import sys

# Ensure UTF-8 output encoding for Windows stdout
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print('[+] Packing Data for Google Colab/Kaggle...')
print('=============================================')

output_filename = 'colab_training_package.zip'

with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
    # 1. Add Data files (We skip 1m data to keep the file size small and fast to upload)
    patterns = [
        'data/*_5m_historical.csv',
        'data/*_1h_historical.csv', 
        'data/*_sentiment_2019_2026.csv', 
        'data/*_funding.csv',
        'data/macro_daily.csv'
    ]
    
    print("\n[*] Adding Historical Price & Sentiment Data...")
    for pattern in patterns:
        for file in glob.glob(pattern):
            print(f'  -> {file}')
            zipf.write(file, arcname=file)
            
    # 2. Add Required Python Scripts
    print("\n[*] Adding AI Training Scripts...")
    
    script_patterns = [
        'training/*.py',
        'backtesting/*.py',
        'agents/*.py',
        'models/*.py'
    ]
    
    for pattern in script_patterns:
        for script in glob.glob(pattern):
            print(f'  -> {script}')
            zipf.write(script, arcname=script)

print(f'\n✅ Success! You can now upload "{output_filename}" to Google Colab!')

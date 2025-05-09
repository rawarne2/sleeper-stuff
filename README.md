# KeepTradeCut Scraper

A simple script to scrape player values from KeepTradeCut.com for fantasy football.

## Installation

1. Clone this repository
2. Create a virtual environment (optional but recommended):

   ```
   python -m venv sleeper_env
   source sleeper_env/bin/activate  # On Windows: sleeper_env\Scripts\activate
   ```

3. Install dependencies:

   ```
   pip install -r requirements.txt
   ```

**Note:** On some systems (especially macOS and Linux), you may need to use `python3` and `pip3` instead of `python` and `pip` if Python 2 is also installed. You can check your Python version with `python --version` or `python3 --version`.

## Usage

Run the script with:

```
python ktc-scrape.py
```

This will scrape player values from KeepTradeCut and export the data to a CSV file (ktc.csv)

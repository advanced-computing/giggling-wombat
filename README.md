## The Correlation between Weekly U.S. Petroleum Product Supplied and WTI Crude Oil Price Dashboard
team: giggling wombat

This project analyzes weekly U.S. petroleum product supplied data and WTI crude oil spot price data using the EIA API. Our goal is to explore how petroleum supply and crude oil prices evolve over time and whether they exhibit similar patterns during major economic or energy market events.

<a target="_blank" href="https://colab.research.google.com/github/advanced-computing/giggling-wombat/blob/main/project.ipynb">
  <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"/>
</a>

## Data Loading Approach

We use batch loading for this project. Our data comes from the EIA API and is updated weekly, so real-time streaming is not necessary. We use a local Python script (`load_to_bigquery.py`) to pull data from the API and load it into BigQuery tables. The Streamlit app then reads from BigQuery instead of calling the API directly. This approach improves reliability, simplifies deployment, and helps the app load faster.

### What dataset are you going to use?

Weekly U.S. Petroleum Product Supplied https://www.eia.gov/opendata/browser/petroleum/cons/wpsup

Weekly WTI Crude Oil Spot Price (RWTC) https://www.eia.gov/opendata/browser/petroleum/pri/spt

### What are your research question(s)?

- How has U.S. petroleum product supplied changed since 2012?
- How has WTI crude oil price changed over the same period?
- Do petroleum supply and crude oil prices show similar patterns over time?
- Are there noticeable disruptions during major events such as the COVID-19 period?

### Link to notebook: https://github.com/advanced-computing/giggling-wombat/blob/main/project.ipynb

### Target Visualization Description

- Weekly time-series line chart of U.S. petroleum product supplied
- Weekly time-series line chart of WTI crude oil price
- Visual comparison of trends between the two series


### What are your known unknowns?

- Petroleum product supplied is a proxy for demand rather than a direct measure
- Weekly data can be noisy and may obscure long-term trends
- Oil prices and supply may react to different economic forces
- The project depends on API data retrieval instead of downloadable CSV files

### What challenges do you anticipate?

Short-term volatility may obscure longer-term patterns

Interpreting whether observed changes reflect demand-side behavior or reporting adjustments

So many events that distort oil supply every day, it is challenging to specify all of the events

The data source does not support direct CSV downloads, requiring the use of an API. This presents a challenge for my typical workflow, which usually begins with a downloaded CSV file to start a project.

### Project Structure

- `Homepage.py`  
  Main dashboard page for weekly U.S. petroleum product supplied.

- `pages/2_WTI_Price.py`  
  Secondary dashboard page for WTI crude oil prices.

- `load_to_bigquery.py`  
  Script for pulling data from the EIA API and loading it into BigQuery.

### Prerequisites

Before running this project, make sure you have:

- Python 3.10 or newer
- `pip`
- A Google account with access to the course Google Cloud project
- A BigQuery dataset in the course project
- An EIA API key
- A service account JSON key for the Streamlit app

## Setup instructions
```bash

### 1. Clone the Repository
git clone <YOUR_REPO_URL>
cd giggling-wombat

2. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

3. Install dependencies
pip install -r requirements.txt

4. Set your EIA API key

Before running the load script, export your EIA API key:

export EIA_API_KEY="your_eia_api_key"

5. Authenticate with Google Cloud

Run the following command and log in with your Columbia Google account:

gcloud auth application-default login

6. Load data into BigQuery

Run:
python3 load_to_bigquery.py

This script loads data into the following BigQuery tables:

petroleum_supply.weekly_supply
petroleum_supply.weekly_supply_by_product
petroleum_supply.weekly_wti

The Google Cloud project used in this project is:

sipa-adv-c-giggling-wombat

The BigQuery dataset used in this project is:

petroleum_supply

7. Create local Streamlit secrets

Create a file at:

.streamlit/secrets.toml

Add the following into your secrets: (please reach to us in person and we can give you the key!)

Make sure .streamlit/secrets.toml is included in .gitignore so it is not committed to GitHub.

8. Run the app locally
streamlit run Homepage.py
# Vinted Profit Identifier

Scrapes vinted search results to find profitable items for resell on CeX

## Setup

1.  **Env variables**:
    ```
    OPENAI_API_KEY="your_openai_api_key_here"
    ```

2.  **Configuration**: Set the required paths in `config.py` `CHROMEDRIVER_PATH`, `CHROME_PROFILE_PATH` and `SEARCH_TERMS`. Lower `MAX_WORKERS` if you're being rate limited

## Entry point

```bash
python main.py
```
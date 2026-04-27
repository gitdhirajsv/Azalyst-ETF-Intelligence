import os
from pathlib import Path

def generate_env_example():
    """
    Generates/Updates .env.example based on config.py and current .env
    """
    # Keys we want to include in .env.example
    keys_to_include = [
        "DISCORD_WEBHOOK_URL",
        "NVIDIA_API_KEY",
        "PORTFOLIO_FILE",
        "STATE_FILE",
        "NEWS_API_KEY",
        "AV_API_KEY",
        "FINNHUB_API_KEY"
    ]
    
    root = Path(__file__).parent.parent
    env_example_path = root / ".env.example"
    
    content = "# Azalyst ETF Intelligence - Environment Variables Template\n"
    content += "# Copy this to .env and fill in your keys\n\n"
    
    for key in keys_to_include:
        content += f"{key}=\n"
        
    with open(env_example_path, "w") as f:
        f.write(content)
        
    print(f"Generated {env_example_path}")

if __name__ == "__main__":
    generate_env_example()

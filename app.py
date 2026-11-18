"""
app.py - Entry point. Run this file to start the Qless web server.
"""

from flask import Flask

from config import Config

# Create the Flask app and load all settings from config.py
app = Flask(__name__)
app.config.from_object(Config)


@app.route("/health")
def health_check():
    # A simple page to confirm the server is running
    return "Qless is running. Less Waiting. Less Waste. Better Campus."


if __name__ == "__main__":
    app.run(debug=Config.DEBUG)
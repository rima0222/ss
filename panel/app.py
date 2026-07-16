from flask import Flask, jsonify
app=Flask(__name__)

@app.route("/")
def home():
    return "Custom Panel Production v1"

@app.route("/api/health")
def health():
    return jsonify({"status":"ok"})

app.run(host="0.0.0.0",port=5000)

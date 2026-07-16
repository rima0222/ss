from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def index():
    return "Custom Panel v16"

@app.route("/api/status")
def status():
    return jsonify({
        "version":"16.0",
        "status":"running"
    })

if __name__=="__main__":
    app.run(host="0.0.0.0",port=5000)

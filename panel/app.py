from flask import Flask, jsonify

app = Flask(__name__)

@app.get('/api/health')
def health():
    return jsonify({
        'version':'15.0.0',
        'status':'ok'
    })
